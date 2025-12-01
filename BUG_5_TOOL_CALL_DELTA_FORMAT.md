# Bug #5: Неправильный формат response.tool_call.delta

**Дата обнаружения**: 2025-11-24
**Приоритет**: 🔴 **CRITICAL**
**Статус**: ❌ **NOT FIXED**
**Связанные файлы**:
- `vllm/entrypoints/openai/protocol.py:2600-2618`
- `vllm/entrypoints/openai/serving_responses.py:664-686`

---

## Executive Summary

vLLM отправляет **объекты** в `delta.content` для событий `response.tool_call.delta`, в то время как спецификация OpenAI **требует массив строк**. Это ломает десериализацию в OpenAI SDK и других клиентах, вызывая ошибку типа `invalid type: map, expected a string`.

**Impact**: 🔴 **BREAKING** - полностью ломает совместимость с OpenAI Codex и другими клиентами при streaming tool calls.

---

## Спецификация OpenAI Responses API

### Требуемый формат

Согласно официальной спецификации OpenAI Responses API:

```json
{
  "type": "response.tool_call.delta",
  "response": { "id": "resp_xxx" },
  "delta": {
    "content": [
      "<строка с очередным кусочком аргументов>"
    ]
  },
  "sequence_number": 42
}
```

**Ключевые требования**:

1. ✅ `delta.content` — **массив строк**, а не объектов
2. ✅ Каждая строка — кусочек JSON (или текста) аргументов
3. ✅ Клиент конкатенирует строки, затем парсит целиком как JSON
4. ✅ После всех delta событий отправляется `response.tool_call.completed`

### Пример корректной последовательности событий

```json
// Event 1: Начало tool call
{
  "type": "response.tool_call.delta",
  "response": {"id": "resp_abc123"},
  "delta": {
    "content": ["{\"type\":\"tool_call\",\"call_id\":\"call_123\",\"name\":\"shell\",\"arguments\":\""]
  },
  "sequence_number": 1
}

// Event 2: Часть аргументов
{
  "type": "response.tool_call.delta",
  "response": {"id": "resp_abc123"},
  "delta": {
    "content": ["{\\\"command\\\":[\\\"bash\\\",\\\"-lc\\\"],"]
  },
  "sequence_number": 2
}

// Event 3: Окончание аргументов
{
  "type": "response.tool_call.delta",
  "response": {"id": "resp_abc123"},
  "delta": {
    "content": ["\\\"stdin\\\":null}\"}]"]
  },
  "sequence_number": 3
}

// Event 4: Завершение tool call
{
  "type": "response.tool_call.completed",
  "response": {"id": "resp_abc123"},
  "delta": {"content": []},
  "sequence_number": 4
}
```

**Клиент собирает**:
```javascript
// Конкатенация всех delta.content[0]:
const fullArgs =
  "{\"type\":\"tool_call\",\"call_id\":\"call_123\",\"name\":\"shell\",\"arguments\":\"" +
  "{\\\"command\\\":[\\\"bash\\\",\\\"-lc\\\"]," +
  "\\\"stdin\\\":null}\"}]";

// Парсинг
const toolCall = JSON.parse(fullArgs);
// => { type: "tool_call", call_id: "call_123", name: "shell", arguments: "{\"command\":[\"bash\",\"-lc\"],\"stdin\":null}" }
```

---

## Текущая реализация vLLM (неправильная)

### Код в protocol.py:2600-2618

```python
class ResponseToolCallDeltaContent(OpenAIBaseModel):
    """Representation of a streaming tool call delta payload."""

    type: Literal["tool_call"] = "tool_call"
    id: str
    call_id: str | None = None
    name: str | None = None
    arguments: str
    status: str | None = None


class ResponseToolCallDeltaEvent(OpenAIBaseModel):
    """OpenAI-compatible response.tool_call.delta streaming event."""

    type: Literal["response.tool_call.delta"] = "response.tool_call.delta"
    response: dict[str, Any]
    delta: dict[str, list[ResponseToolCallDeltaContent]]  # ❌ Массив ОБЪЕКТОВ!
    sequence_number: int
```

**Проблема**: Тип `delta` определен как `dict[str, list[ResponseToolCallDeltaContent]]` — массив **объектов**, а не строк!

### Код в serving_responses.py:664-686

```python
def _build_tool_call_delta_event(
    self,
    *,
    response_id: str,
    tool_call_id: str,
    tool_name: str | None,
    arguments_delta: str,
) -> ResponseToolCallDeltaEvent:
    """Create an OpenAI-compatible response.tool_call.delta event."""

    # ❌ Создается объект вместо строки!
    content = ResponseToolCallDeltaContent(
        id=tool_call_id,
        call_id=tool_call_id,
        name=tool_name,
        arguments=arguments_delta,  # Это строка, но она упакована в объект!
        status="in_progress",
    )

    # ❌ Объект помещается в delta.content
    return ResponseToolCallDeltaEvent(
        type="response.tool_call.delta",
        response={"id": response_id},
        delta={"content": [content]},  # [объект] вместо [строка]!
        sequence_number=-1,
    )
```

### Что отправляется клиенту (неправильно)

```json
{
  "type": "response.tool_call.delta",
  "response": {"id": "resp_abc123"},
  "delta": {
    "content": [
      {
        "type": "tool_call",
        "id": "call_456",
        "call_id": "call_456",
        "name": "shell",
        "arguments": "{\n",
        "status": "in_progress"
      }
    ]
  },
  "sequence_number": 42
}
```

**Проблема**: `delta.content[0]` — это **объект** (map), а не строка!

---

## Почему это ломает клиентов

### OpenAI SDK (Python/JavaScript)

OpenAI SDK ожидает:
```python
# Python
for event in stream:
    if event.type == "response.tool_call.delta":
        # Ожидается строка
        delta_chunk: str = event.delta.content[0]
        buffer += delta_chunk
```

При получении объекта вместо строки:
```python
TypeError: can only concatenate str (not "dict") to str
# или
json.decoder.JSONDecodeError: invalid type: map, expected a string
```

### OpenAI Codex

Из логов:
```
Deserialization error: invalid type: map at line ... column ...
Expected value type: String
Actual value: {"type":"tool_call","id":"call_...","call_id":"call_...","name":"shell","arguments":"{\\n","status":"in_progress"}
```

Codex пытается десериализовать `delta.content[0]` как строку, но получает объект.

### Последствия

- ❌ Невозможно использовать streaming tool calls с OpenAI SDK
- ❌ Ломается интеграция с Codex
- ❌ Любой клиент, следующий спецификации OpenAI, получит ошибку
- ❌ Non-streaming работает (там полный объект в `output`), но streaming - нет

---

## Правильная реализация

### 1. Изменить тип в protocol.py

```python
class ResponseToolCallDeltaEvent(OpenAIBaseModel):
    """OpenAI-compatible response.tool_call.delta streaming event."""

    type: Literal["response.tool_call.delta"] = "response.tool_call.delta"
    response: dict[str, Any]
    delta: dict[str, list[str]]  # ✅ Массив СТРОК!
    sequence_number: int
```

**Удалить** `ResponseToolCallDeltaContent` класс, так как он не нужен для streaming delta.

### 2. Изменить логику в serving_responses.py

#### Вариант A: Отправить все аргументы одним куском (простой)

```python
def _build_tool_call_delta_event(
    self,
    *,
    response_id: str,
    tool_call_id: str,
    tool_name: str | None,
    arguments: str,  # Полные аргументы JSON
) -> ResponseToolCallDeltaEvent:
    """Create an OpenAI-compatible response.tool_call.delta event."""

    # Формируем JSON-строку с полным tool call
    tool_call_json = json.dumps({
        "type": "tool_call",
        "call_id": tool_call_id,
        "name": tool_name,
        "arguments": arguments
    })

    # ✅ Отправляем как строку в массиве
    return ResponseToolCallDeltaEvent(
        type="response.tool_call.delta",
        response={"id": response_id},
        delta={"content": [tool_call_json]},  # [строка]!
        sequence_number=-1,
    )
```

#### Вариант B: Streaming по кускам (сложнее, но точнее)

Если хотите настоящий streaming (по мере генерации):

```python
def _build_tool_call_delta_event(
    self,
    *,
    response_id: str,
    arguments_chunk: str,  # Кусочек аргументов
    is_first: bool = False,
    is_last: bool = False,
    tool_call_id: str | None = None,
    tool_name: str | None = None,
) -> ResponseToolCallDeltaEvent:
    """Create streaming tool call delta event."""

    if is_first:
        # Первый chunk: открываем структуру
        prefix = json.dumps({
            "type": "tool_call",
            "call_id": tool_call_id,
            "name": tool_name,
            "arguments": ""
        })[:-2]  # Убираем ""}

        chunk = f'{prefix}{json.dumps(arguments_chunk)[1:-1]}'
    elif is_last:
        # Последний chunk: закрываем
        chunk = f'{json.dumps(arguments_chunk)[1:-1]}"}}'
    else:
        # Промежуточный chunk
        chunk = json.dumps(arguments_chunk)[1:-1]  # Убираем кавычки

    return ResponseToolCallDeltaEvent(
        type="response.tool_call.delta",
        response={"id": response_id},
        delta={"content": [chunk]},  # [строка]!
        sequence_number=-1,
    )
```

### 3. Обновить места вызова

Найти все места, где вызывается `_build_tool_call_delta_event`, и передавать строки:

```bash
grep -n "_build_tool_call_delta_event" vllm/entrypoints/openai/serving_responses.py
```

---

## Связь с другими багами

### Bug #4: Delta format для output_text

**Bug #4** был про формат `delta` в `response.output_text.delta` — там требовалась **строка**, а не объект `{"type": "text", "text": "..."}`.

**Bug #5** — аналогичная проблема, но для `response.tool_call.delta`. Паттерн тот же:
- ❌ vLLM отправляет структурированные объекты
- ✅ OpenAI требует строки

### Общая причина

Видимо, при разработке vLLM предположили, что структурированные объекты удобнее для parsing, но это нарушает спецификацию OpenAI. OpenAI использует строки в delta, потому что:

1. **Streaming** — можно отправлять частями по мере генерации
2. **Простота** — клиент просто конкатенирует строки
3. **Гибкость** — можно стримить любой формат (JSON, plain text, и т.д.)

---

## Тестирование после исправления

### 1. Unit test

```python
def test_tool_call_delta_format():
    """Test that tool_call.delta sends strings, not objects."""
    event = _build_tool_call_delta_event(
        response_id="resp_123",
        tool_call_id="call_456",
        tool_name="shell",
        arguments='{"command":["bash","-lc"]}'
    )

    # Check type
    assert isinstance(event.delta["content"], list)
    assert len(event.delta["content"]) == 1
    assert isinstance(event.delta["content"][0], str)  # ✅ Строка!

    # Check parseable JSON
    parsed = json.loads(event.delta["content"][0])
    assert parsed["type"] == "tool_call"
    assert parsed["call_id"] == "call_456"
    assert parsed["name"] == "shell"
```

### 2. Integration test с OpenAI SDK

```python
import openai

client = openai.OpenAI(base_url="http://localhost:8000/v1")

stream = client.responses.create(
    model="gpt-4o",
    input="Run 'ls -la' command",
    tools=[{"type": "function", "function": {...}}],
    stream=True
)

buffer = ""
for event in stream:
    if event.type == "response.tool_call.delta":
        # Должно работать без ошибок
        chunk = event.delta.content[0]
        assert isinstance(chunk, str)
        buffer += chunk

# Parse полный результат
tool_call = json.loads(buffer)
assert tool_call["name"] == "shell"
```

### 3. Test с Codex

Запустить vLLM с исправлением и проверить Codex:
```bash
# Codex должен успешно парсить tool calls
codex-client --endpoint http://localhost:8000/v1 --stream
```

---

## Приоритет исправления

**🔴 CRITICAL** — должно быть исправлено немедленно, потому что:

1. **Ломает базовую функциональность** — streaming tool calls не работают
2. **Блокирует интеграцию** с OpenAI SDK и Codex
3. **Breaking change** для всех клиентов, использующих спецификацию OpenAI
4. **Легко исправить** — изменить тип и формат в 2 файлах

---

## Roadmap

### Немедленно (сегодня)

1. Изменить `ResponseToolCallDeltaEvent.delta` тип на `dict[str, list[str]]`
2. Удалить или переименовать `ResponseToolCallDeltaContent` (он для non-streaming)
3. Обновить `_build_tool_call_delta_event` для отправки строк
4. Запустить unit tests

### Через 1 день

5. Integration tests с OpenAI SDK
6. Тест с Codex
7. Обновить SPEC_TO_CODE_MAPPING.json
8. Обновить compliance reports

### Через неделю

9. Проверить другие delta события на аналогичные проблемы
10. Code review + PR
11. Документация изменений

---

## Сравнение: До и После

### До (неправильно) ❌

```python
# protocol.py
delta: dict[str, list[ResponseToolCallDeltaContent]]

# serving_responses.py
content = ResponseToolCallDeltaContent(...)
return ResponseToolCallDeltaEvent(
    delta={"content": [content]}  # объект
)

# Что отправляется
{
  "delta": {
    "content": [{"type": "tool_call", "id": "...", ...}]  # объект
  }
}
```

**Результат**: ❌ OpenAI SDK ломается

### После (правильно) ✅

```python
# protocol.py
delta: dict[str, list[str]]

# serving_responses.py
tool_call_json = json.dumps({...})
return ResponseToolCallDeltaEvent(
    delta={"content": [tool_call_json]}  # строка
)

# Что отправляется
{
  "delta": {
    "content": ["{\"type\":\"tool_call\",\"id\":\"...\",\"name\":\"...\"}"]  # строка
  }
}
```

**Результат**: ✅ OpenAI SDK работает, Codex парсит корректно

---

## Связанные документы

- **Bug #4**: `BUGFIX_REPORT_20251124_delta_format.md` - аналогичная проблема для output_text
- **OpenAI Spec**: `DOC_streaming_events.md` - спецификация streaming events
- **SPEC_TO_CODE_MAPPING.json**: Нужно обновить статус `response.tool_call.delta`
- **COMPLIANCE_PLAN_GAPS_REPORT.md**: Добавить Bug #5 в список проблем

---

## Дополнительные замечания

### Почему объекты не работают

OpenAI SDK ожидает **минимальную структуру** в streaming:
- Только ID ответа в `response`
- Только строки в `delta.content`
- Вся структурированная информация передается **после завершения** в `response.tool_call.completed` или в non-streaming ответе

Streaming предназначен для **постепенной передачи данных**, поэтому используются примитивные типы (строки), которые легко конкатенировать.

### Нестриминговые ответы

Для **non-streaming** (когда `stream=False`) можно использовать полные объекты:

```python
# Non-streaming response.output
{
  "output": [
    {
      "type": "message",
      "content": [
        {
          "type": "tool_call",
          "id": "call_123",
          "name": "shell",
          "arguments": "{...}"
        }
      ]
    }
  ]
}
```

Здесь объект `tool_call` допустим, потому что это финальный результат, а не delta.

---

**Конец отчета**

Дата: 2025-11-24
Автор: Claude Code
Приоритет: 🔴 CRITICAL
Статус: ❌ NOT FIXED
