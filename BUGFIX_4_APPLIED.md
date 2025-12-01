# Bug Fix #4 - SSE Delta Format Incompatibility

## Дата применения: 2025-11-24
## Статус: ✅ **ИСПРАВЛЕНО В КОДЕ**

---

## Резюме проблемы

OpenAI-совместимый клиент не мог парсить SSE события от vLLM сервера из-за неправильного формата поля `delta`:
- **vLLM отправлял:** `"delta": {"content": "text"}` (объект)
- **Клиент ожидал:** `"delta": "text"` (строка)

Это приводило к 46+ ошибкам парсинга и преждевременному закрытию потока.

---

## Применённые исправления

### ✅ 1. Исправлен тип `delta` в `protocol.py`

#### Изменение 1: `ResponseReasoningDeltaEvent` (строка 2551-2555)

**Было:**
```python
delta: dict[str, str] = Field(
    ...,
    description="Incremental reasoning payload.",
    examples=[{"content": "Step 1: analyzing repository structure..."}],
)
```

**Стало:**
```python
delta: str = Field(
    ...,
    description="Incremental reasoning payload.",
    examples=["Step 1: analyzing repository structure..."],
)
```

**Файл:** `vllm/entrypoints/openai/protocol.py:2551`

---

#### Изменение 2: `ResponseReasoningSummaryDeltaEvent` (строка 2586-2590)

**Было:**
```python
delta: dict[str, str] = Field(
    ...,
    description="Incremental summary payload.",
    examples=[{"summary": "Analyzed repository structure and found TODOs."}],
)
```

**Стало:**
```python
delta: str = Field(
    ...,
    description="Incremental summary payload.",
    examples=["Analyzed repository structure and found TODOs."],
)
```

**Файл:** `vllm/entrypoints/openai/protocol.py:2586`

---

### ✅ 2. Исправлена генерация событий в `serving_responses.py`

#### Изменение 3: Генерация `ResponseReasoningDeltaEvent` (строка 596)

**Было:**
```python
return ResponseReasoningDeltaEvent(
    type="response.reasoning.delta",
    response={"id": response_id},
    delta={"content": delta_text},  # ❌ Оборачивало в объект
    sequence_number=-1,
)
```

**Стало:**
```python
return ResponseReasoningDeltaEvent(
    type="response.reasoning.delta",
    response={"id": response_id},
    delta=delta_text,  # ✅ Передаём напрямую
    sequence_number=-1,
)
```

**Файл:** `vllm/entrypoints/openai/serving_responses.py:596`

---

#### Изменение 4: Генерация `ResponseReasoningSummaryDeltaEvent` (строка 675)

**Было:**
```python
ResponseReasoningSummaryDeltaEvent(
    type="response.reasoning.summary.delta",
    response={"id": response_id},
    delta={"summary": chunk},  # ❌ Оборачивало в объект
    sequence_number=-1,
)
```

**Стало:**
```python
ResponseReasoningSummaryDeltaEvent(
    type="response.reasoning.summary.delta",
    response={"id": response_id},
    delta=chunk,  # ✅ Передаём напрямую
    sequence_number=-1,
)
```

**Файл:** `vllm/entrypoints/openai/serving_responses.py:675`

---

## Ожидаемый результат

После перезапуска сервера SSE события будут иметь правильный формат:

**До исправления:**
```json
{
  "type": "response.reasoning.delta",
  "response": {"id": "resp_xxx"},
  "delta": {"content": "We"},  // ❌ Клиент не может распарсить
  "sequence_number": 4
}
```

**После исправления:**
```json
{
  "type": "response.reasoning.delta",
  "response": {"id": "resp_xxx"},
  "delta": "We",  // ✅ Клиент успешно парсит
  "sequence_number": 4
}
```

---

## ⚠️ ТРЕБУЕТСЯ: Перезапуск сервера

**Изменения применены только в файлах. Сервер должен быть перезапущен.**

### Команды перезапуска:

```bash
# 1. Остановить текущий сервер
pkill -f "vllm.entrypoints.openai.api_server"

# Или остановить конкретный процесс
kill 480331  # Замените на актуальный PID

# 2. Запустить с новым кодом
python -m vllm.entrypoints.openai.api_server \
    --model <YOUR_MODEL> \
    --host 0.0.0.0 \
    --port 8000
```

---

## Проверка работы

### 1. Тестовый запрос с reasoning моделью

```bash
curl -X POST http://localhost:8000/v1/responses \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "model": "your-reasoning-model",
    "input": "Analyze this: What is 2+2?",
    "stream": true,
    "max_output_tokens": 100
  }'
```

### 2. Ожидаемый SSE поток

```
event: response.created
data: {"type":"response.created","response":{"id":"resp_xxx",...}}

event: response.reasoning.delta
data: {"type":"response.reasoning.delta","response":{"id":"resp_xxx"},"delta":"Step","sequence_number":1}

event: response.reasoning.delta
data: {"type":"response.reasoning.delta","response":{"id":"resp_xxx"},"delta":" 1:","sequence_number":2}

event: response.reasoning.delta
data: {"type":"response.reasoning.delta","response":{"id":"resp_xxx"},"delta":" Analyzing","sequence_number":3}

...

event: response.completed
data: {"type":"response.completed",...}

data: [DONE]
```

### 3. Проверить логи клиента

**Должны отсутствовать:**
```
❌ Failed to parse SSE event: invalid type: map, expected a string
❌ stream disconnected before completion
```

**Должны присутствовать:**
```
✅ Successfully parsed all SSE events
✅ Received response.completed event
✅ Stream closed gracefully
```

---

## Связь с другими исправлениями

| Баг | Файл | Строка | Статус |
|-----|------|--------|--------|
| 1. NameError: `time` not defined | `api_server.py` | 10 | ✅ Fixed |
| 2. TypeError: unexpected `session` | `serving_responses.py` | 3236 | ✅ Fixed |
| 3. UnboundLocalError: `sequence_number` | `api_server.py` | 708 | ✅ Fixed |
| 4. Delta format incompatibility | `protocol.py`, `serving_responses.py` | 2551, 2586, 596, 675 | ✅ **Fixed** |

---

## Примечание: ResponseToolCallDeltaEvent

**Не изменено:** `ResponseToolCallDeltaEvent` (protocol.py:2532-2538)

```python
class ResponseToolCallDeltaEvent(OpenAIBaseModel):
    delta: dict[str, list[ResponseToolCallDeltaContent]]
```

**Причина:**
- Клиентские логи не показывали ошибок парсинга для tool_call событий
- Tool call события имеют более сложную структуру чем text delta
- Требуется дополнительная проверка по спецификации OpenAI Responses API

Если после тестирования обнаружатся проблемы с tool_call событиями, потребуется дополнительное исследование.

---

## Тестирование

### Рекомендуемые тесты:

```bash
# 1. Compliance тест для streaming
pytest tests/compliance/test_openai_responses_api.py::test_streaming_responses_emits_done -v

# 2. Тесты для reasoning outputs
pytest tests/entrypoints/openai/test_serving_responses.py -k "reasoning" -v

# 3. Полный набор Responses API тестов
pytest tests/entrypoints/openai/test_serving_responses.py -v
```

---

## Статус

| Аспект | Статус |
|--------|--------|
| Код исправлен | ✅ Да |
| Сервер перезапущен | ⚠️ **ТРЕБУЕТСЯ** |
| Протестировано | ⚠️ После перезапуска |
| OpenAI compatibility | ✅ Соответствует спецификации |

---

## Ссылки

- **Полный отчёт:** `BUGFIX_REPORT_4.md`
- **OpenAI Specification:** https://platform.openai.com/docs/api-reference/responses-streaming
- **Related GitHub Issue:** https://github.com/openai/openai-python/issues/2634 (упомянуто в комментариях кода)

---

## Итог

✅ **Все 4 критических изменения применены в коде**

⚠️ **Следующий шаг:** Перезапустить vLLM сервер для применения исправлений

После перезапуска OpenAI-совместимые клиенты смогут корректно парсить все SSE события и streaming будет работать стабильно.
