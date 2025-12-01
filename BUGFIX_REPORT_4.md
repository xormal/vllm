# Bug Report #4: SSE Delta Format Incompatibility

## Дата: 2025-11-24
## Компонент: OpenAI Responses API Streaming
## Критичность: 🔴 CRITICAL - Клиент не может парсить SSE события

---

## Проблема: Несовместимость формата поля `delta`

**Симптомы:**
- OpenAI-совместимый клиент не может распарсить SSE события
- Ошибка: `invalid type: map, expected a string`
- Stream disconnects before completion
- 46+ событий с ошибками парсинга

**Лог клиента:**
```
Failed to parse SSE event: invalid type: map, expected a string at line 1 column 101
data: {"type":"response.reasoning.delta","response":{"id":"resp_..."},"delta":{"content":"We"},"sequence_number":4}
                                                                                   ^^^^^^^^^^^^^^^^
stream disconnected before completion: stream closed before response.completed
```

---

## Корневая причина

### Что отправляет vLLM сервер:
```json
{
  "type": "response.reasoning.delta",
  "delta": {"content": "We"}  // ❌ Объект (map)
}
```

### Что ожидает OpenAI-совместимый клиент (по спецификации):
```json
{
  "type": "response.reasoning.delta",
  "delta": "We"  // ✅ Строка
}
```

**Источник:** [OpenAI Responses API Specification](https://platform.openai.com/docs/api-reference/responses-streaming)

Согласно официальной документации OpenAI:
> The delta field contains the text difference since the last event. The delta field itself is a **string** containing an incremental chunk of the generated text.

---

## Анализ кода

### 1. Некорректные определения в `protocol.py`

#### `ResponseReasoningDeltaEvent` (строка 2543-2556):
```python
class ResponseReasoningDeltaEvent(OpenAIBaseModel):
    """OpenAI-compatible reasoning.delta streaming event."""

    type: Literal["response.reasoning.delta"] = "response.reasoning.delta"
    response: dict[str, Any] = Field(...)
    delta: dict[str, str] = Field(  # ❌ НЕПРАВИЛЬНО - должно быть str
        ...,
        description="Incremental reasoning payload.",
        examples=[{"content": "Step 1: analyzing repository structure..."}],
    )
    sequence_number: int
```

**Проблема:** `delta: dict[str, str]` вместо `delta: str`

#### `ResponseReasoningSummaryDeltaEvent` (строка 2579-2591):
```python
class ResponseReasoningSummaryDeltaEvent(OpenAIBaseModel):
    """OpenAI-compatible reasoning.summary.delta streaming event."""

    type: Literal["response.reasoning.summary.delta"] = "response.reasoning.summary.delta"
    response: dict[str, Any]
    delta: dict[str, str] = Field(  # ❌ НЕПРАВИЛЬНО - должно быть str
        ...,
        description="Incremental summary payload.",
        examples=[{"summary": "Analyzed repository structure and found TODOs."}],
    )
    sequence_number: int
```

**Проблема:** `delta: dict[str, str]` вместо `delta: str`

### 2. Некорректная генерация событий в `serving_responses.py`

#### Генерация `ResponseReasoningDeltaEvent` (строка 593-596):
```python
return ResponseReasoningDeltaEvent(
    type="response.reasoning.delta",
    response={"id": response_id},
    delta={"content": delta_text},  # ❌ НЕПРАВИЛЬНО - оборачивает в объект
    sequence_number=sequence_number,
)
```

**Должно быть:**
```python
return ResponseReasoningDeltaEvent(
    type="response.reasoning.delta",
    response={"id": response_id},
    delta=delta_text,  # ✅ ПРАВИЛЬНО - просто строка
    sequence_number=sequence_number,
)
```

#### Генерация `ResponseReasoningSummaryDeltaEvent` (строка 672-675):
```python
ResponseReasoningSummaryDeltaEvent(
    type="response.reasoning.summary.delta",
    response={"id": response_id},
    delta={"summary": chunk},  # ❌ НЕПРАВИЛЬНО - оборачивает в объект
    sequence_number=sequence_number,
)
```

**Должно быть:**
```python
ResponseReasoningSummaryDeltaEvent(
    type="response.reasoning.summary.delta",
    response={"id": response_id},
    delta=chunk,  # ✅ ПРАВИЛЬНО - просто строка
    sequence_number=sequence_number,
)
```

### 3. Возможная проблема с `ResponseToolCallDeltaEvent`

**Текущее определение (protocol.py:2532-2538):**
```python
class ResponseToolCallDeltaEvent(OpenAIBaseModel):
    """OpenAI-compatible response.tool_call.delta streaming event."""

    type: Literal["response.tool_call.delta"] = "response.tool_call.delta"
    response: dict[str, Any]
    delta: dict[str, list[ResponseToolCallDeltaContent]]  # ⚠️ Требует проверки
    sequence_number: int
```

**Генерация (serving_responses.py:644-647):**
```python
return ResponseToolCallDeltaEvent(
    type="response.tool_call.delta",
    response={"id": response_id},
    delta={"content": [content]},  # ⚠️ Требует проверки по спецификации
    sequence_number=sequence_number,
)
```

**Примечание:** Для tool_call события может иметь более сложную структуру. Требуется проверка по официальной спецификации OpenAI.

---

## Затронутые файлы

| Файл | Строки | Что нужно исправить |
|------|--------|---------------------|
| `vllm/entrypoints/openai/protocol.py` | 2551 | `delta: dict[str, str]` → `delta: str` |
| `vllm/entrypoints/openai/protocol.py` | 2586 | `delta: dict[str, str]` → `delta: str` |
| `vllm/entrypoints/openai/serving_responses.py` | 596 | `delta={"content": delta_text}` → `delta=delta_text` |
| `vllm/entrypoints/openai/serving_responses.py` | 675 | `delta={"summary": chunk}` → `delta=chunk` |

---

## Последствия

| Аспект | Статус |
|--------|--------|
| HTTP Response | ✅ 200 OK (отправляется) |
| SSE Events | ❌ INVALID FORMAT |
| Client parsing | ❌ FAILS (46+ errors) |
| Stream completion | ❌ DISCONNECTS |
| OpenAI compatibility | ❌ BROKEN |
| All reasoning models | ❌ AFFECTED |

**Критичность:** Полностью ломает совместимость с OpenAI-клиентами для reasoning моделей.

---

## Решение

### Шаг 1: Исправить типы в `protocol.py`

#### Файл: `vllm/entrypoints/openai/protocol.py`

**Исправление 1 (строка 2551):**
```python
# Было:
delta: dict[str, str] = Field(
    ...,
    description="Incremental reasoning payload.",
    examples=[{"content": "Step 1: analyzing repository structure..."}],
)

# Должно быть:
delta: str = Field(
    ...,
    description="Incremental reasoning payload.",
    examples=["Step 1: analyzing repository structure..."],
)
```

**Исправление 2 (строка 2586):**
```python
# Было:
delta: dict[str, str] = Field(
    ...,
    description="Incremental summary payload.",
    examples=[{"summary": "Analyzed repository structure and found TODOs."}],
)

# Должно быть:
delta: str = Field(
    ...,
    description="Incremental summary payload.",
    examples=["Analyzed repository structure and found TODOs."],
)
```

### Шаг 2: Исправить генерацию событий в `serving_responses.py`

#### Файл: `vllm/entrypoints/openai/serving_responses.py`

**Исправление 1 (строка 593-597):**
```python
# Было:
return ResponseReasoningDeltaEvent(
    type="response.reasoning.delta",
    response={"id": response_id},
    delta={"content": delta_text},
    sequence_number=sequence_number,
)

# Должно быть:
return ResponseReasoningDeltaEvent(
    type="response.reasoning.delta",
    response={"id": response_id},
    delta=delta_text,  # Убрали обёртку {"content": ...}
    sequence_number=sequence_number,
)
```

**Исправление 2 (строка 672-676):**
```python
# Было:
ResponseReasoningSummaryDeltaEvent(
    type="response.reasoning.summary.delta",
    response={"id": response_id},
    delta={"summary": chunk},
    sequence_number=sequence_number,
)

# Должно быть:
ResponseReasoningSummaryDeltaEvent(
    type="response.reasoning.summary.delta",
    response={"id": response_id},
    delta=chunk,  # Убрали обёртку {"summary": ...}
    sequence_number=sequence_number,
)
```

---

## Проверка исправления

### 1. После применения патча перезапустить сервер:
```bash
pkill -f "vllm.entrypoints.openai.api_server"
python -m vllm.entrypoints.openai.api_server --model <MODEL>
```

### 2. Тестовый запрос:
```bash
curl -X POST http://localhost:8000/v1/responses \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "model": "your-model",
    "input": "Test reasoning",
    "stream": true,
    "max_output_tokens": 50
  }'
```

### 3. Ожидаемый результат:
```
event: response.reasoning.delta
data: {"type":"response.reasoning.delta","response":{"id":"resp_xxx"},"delta":"We","sequence_number":4}
                                                                        ^^^^ ✅ Строка, не объект

event: response.reasoning.delta
data: {"type":"response.reasoning.delta","response":{"id":"resp_xxx"},"delta":" are","sequence_number":5}

...

event: response.completed
data: {"type":"response.completed",...}

data: [DONE]
```

### 4. Проверить логи клиента:
```
✅ Должны отсутствовать: "Failed to parse SSE event: invalid type: map"
✅ Stream должен завершаться с: "response.completed"
✅ Клиент должен получить весь текст
```

---

## Дополнительные проверки

### Проверить tool_call события

После исправления также проверить, правильно ли работают события `response.tool_call.delta`:

```bash
curl -X POST http://localhost:8000/v1/responses \
  -H "Content-Type: application/json" \
  -d '{
    "model": "your-model",
    "input": "Calculate 2+2",
    "stream": true,
    "tools": [...]
  }'
```

Если клиент также жалуется на tool_call события, потребуется дополнительное исправление.

---

## Связь с другими багами

| Проблема | Файл | Статус |
|----------|------|--------|
| 1. NameError: `time` not defined | `api_server.py:10` | ✅ Fixed |
| 2. TypeError: unexpected `session` | `serving_responses.py:3236` | ✅ Fixed |
| 3. UnboundLocalError: `sequence_number` | `api_server.py:708` | ✅ Fixed в коде, ⚠️ нужен restart |
| 4. Delta format incompatibility | `protocol.py`, `serving_responses.py` | ❌ **ТРЕБУЕТ ИСПРАВЛЕНИЯ** |

---

## Референсы

1. **OpenAI Responses API Documentation:**
   - https://platform.openai.com/docs/api-reference/responses-streaming

2. **Discussions о формате delta:**
   - https://community.openai.com/t/two-different-responses-events-for-reasoning-summary/1285333
   - https://community.openai.com/t/reasoning-text-showing-up-as-responsetextdeltaevent/1360442

3. **vLLM Issue (related):**
   - TODO markers in code: "this code can be removed once openai/openai-python/issues/2634 has been resolved"

---

## Итог

**Статус:** ❌ **КРИТИЧЕСКАЯ ОШИБКА** - требует немедленного исправления

**Действия:**
1. ✅ Корневая причина идентифицирована
2. ✅ Решение описано с точными изменениями
3. ❌ Изменения НЕ применены в коде
4. ❌ Сервер работает с неправильным форматом

**После исправления:**
- OpenAI-клиенты смогут парсить все SSE события
- Stream будет завершаться корректно с `response.completed`
- Reasoning модели заработают в production
