# Bug #5: Анализ на основе логов Codex

**Дата**: 2025-11-25
**Источник**: Логи codex-tui.log от клиента

---

## Фактическое поведение из логов

### Что отправляет vLLM (из SSE лога)

```
data: {"type":"response.tool_call.delta","response":{"id":"resp_e311f2074d5c4fb98d626df3fd525e82"},"delta":{"content":["[{\"type\":\"tool_call\",\"id\":\"call_68bbf232c11f417d936e91bf62c35f63\",\"call_id\":\"call_68bbf232c11f417d936e91bf62c35f63\",\"name\":\"shell\",\"arguments\":\"{\\\""]},"sequence_number":72}
```

После JSON парсинга `delta.content[0]`:
```javascript
[{"type":"tool_call","id":"call_68bbf232c11f417d936e91bf62c35f63","call_id":"call_68bbf232c11f417d936e91bf62c35f63","name":"shell","arguments":"{""}]
```

**Это строка, содержащая JSON массив с объектом!**

### Последующие delta события

```
seq 74: "delta":{"content":["command"]}
seq 76: "delta":{"content":["\\\":[\\\""]}
seq 78: "delta":{"content":["bash"]}
seq 80: "delta":{"content":["\\\",\\\""]}
seq 82: "delta":{"content":["-"]}
seq 84: "delta":{"content":["lc"]}
```

**Наблюдение**: vLLM стримит ЧАСТИ аргументов, но первый delta содержит обёртку tool_call.

### Ошибка Codex

```
Failed to parse SSE event: invalid type: map, expected a string at line 1 column 101
```

---

## Проблема: Несоответствие формата

### Что делает vLLM сейчас (НЕПРАВИЛЬНО)

**Delta 1** (seq 72):
```json
"content": ["[{\"type\":\"tool_call\",\"id\":\"...\",\"name\":\"shell\",\"arguments\":\"{\\\""}]"]
```

После парсинга JSON это **строка**:
```
[{"type":"tool_call","id":"...","name":"shell","arguments":"{""}]
```

Эта строка содержит JSON **массив** с **объектом** tool_call.

**Delta 2-N**: Куски аргументов
```json
"content": ["command"]
"content": ["\":\"["]
"content": ["bash"]
```

**Проблема**:
1. Первый delta содержит обёртку `[{...}]` с частичным полем arguments
2. Последующие delta добавляют части arguments
3. Codex не может склеить это корректно, потому что формат неправильный

### Что ожидает Codex/OpenAI SDK (ПРАВИЛЬНО)

Есть **два варианта** согласно спецификации:

#### Вариант A: Один delta с полным tool call

```json
// Один delta с полным tool call
{
  "type": "response.tool_call.delta",
  "delta": {
    "content": [
      "{\"type\":\"tool_call\",\"call_id\":\"call_123\",\"name\":\"shell\",\"arguments\":\"{\\\"command\\\":[\\\"bash\\\",\\\"-lc\\\"],\\\"stdin\\\":null}\"}"
    ]
  },
  "sequence_number": 1
}
```

После парсинга `delta.content[0]` - это строка:
```
{"type":"tool_call","call_id":"call_123","name":"shell","arguments":"{\"command\":[\"bash\",\"-lc\"],\"stdin\":null}"}
```

Эта строка - JSON **объект** (не массив!), который можно парсить.

#### Вариант B: Streaming по частям (сложнее)

```json
// Delta 1: Начало структуры
{
  "delta": {"content": ["[{"]},
  "sequence_number": 1
}

// Delta 2: Продолжение
{
  "delta": {"content": ["\"type\":\"tool_call\","]},
  "sequence_number": 2
}

// Delta 3: Продолжение
{
  "delta": {"content": ["\"call_id\":\"call_123\","]},
  "sequence_number": 3
}

// ... и так далее до закрывающей скобки
{
  "delta": {"content": ["}]"]},
  "sequence_number": N
}
```

Конкатенация всех `content[0]`:
```
[{ + "type":"tool_call", + "call_id":"call_123", + ... + }]
```

Результат: валидный JSON массив.

---

## Что не так в текущей реализации vLLM

### Проблема 1: Несовместимый формат первого delta

vLLM отправляет:
```json
"content": ["[{\"type\":\"tool_call\",\"id\":\"...\",\"arguments\":\"{\\\""}]"]
```

Это строка: `[{"type":"tool_call","id":"...","arguments":"{""}]`

**Проблемы**:
1. Массив `[...]` вместо объекта `{...}` ?
2. Частичное поле `arguments: "{"` - невалидный JSON
3. Последующие delta просто добавляют текст, не закрывая структуру

### Проблема 2: Codex не может собрать валидный JSON

Если Codex конкатенирует все delta.content:

```
[{"type":"tool_call","id":"...","arguments":"{""}] +
command +
":[" +
bash +
"," +
- +
lc +
...
```

Результат: **невалидный JSON**!

Потому что:
- Первый delta заканчивается на `"]` (закрывает массив)
- Последующие delta добавляются после закрытия
- Получается: `[{...}]command":[bash,-lc...`

### Проблема 3: Ошибка десериализации

Codex пытается парсить каждый delta отдельно или пытается десериализовать структуру delta, и видит что `content[0]` при парсинге даёт map/array вместо простой строки для конкатенации.

---

## Правильное решение

### Решение A: Отправить весь tool call одним delta (простое)

```python
def _build_tool_call_delta_event(
    self,
    *,
    response_id: str,
    tool_call_id: str,
    tool_name: str,
    arguments_json: str,  # Полные аргументы уже в JSON
) -> ResponseToolCallDeltaEvent:
    """Build tool call delta with complete data."""

    # Формируем JSON объект (не массив!)
    tool_call_str = json.dumps({
        "type": "tool_call",
        "call_id": tool_call_id,
        "name": tool_name,
        "arguments": arguments_json
    })

    # Отправляем как ОДНУ строку
    return ResponseToolCallDeltaEvent(
        type="response.tool_call.delta",
        response={"id": response_id},
        delta={"content": [tool_call_str]},  # ОДНА строка с полным объектом
        sequence_number=-1,
    )
```

**Что отправится**:
```json
{
  "delta": {
    "content": [
      "{\"type\":\"tool_call\",\"call_id\":\"call_123\",\"name\":\"shell\",\"arguments\":\"{\\\"command\\\":[\\\"bash\\\",\\\"-lc\\\"],\\\"stdin\\\":null}\"}"
    ]
  }
}
```

После парсинга JSON, `delta.content[0]`:
```
{"type":"tool_call","call_id":"call_123","name":"shell","arguments":"{\"command\":[\"bash\",\"-lc\"],\"stdin\":null}"}
```

Codex может парсить это как объект tool_call.

### Решение B: НЕ использовать массив в первом delta

Текущая проблема: vLLM отправляет `[{...}]` (массив), но по спецификации должен быть объект `{...}`.

Если убрать квадратные скобки:

```python
# Вместо:
tool_call_str = json.dumps([{...}])  # Массив

# Использовать:
tool_call_str = json.dumps({...})  # Объект
```

### Решение C: Streaming по частям (сложнее, но правильнее)

Если нужен настоящий streaming:

```python
def _build_tool_call_deltas(
    self,
    response_id: str,
    tool_call_id: str,
    tool_name: str,
    arguments_chunks: list[str],
) -> list[ResponseToolCallDeltaEvent]:
    """Build streaming tool call deltas."""

    deltas = []

    # Delta 1: Открываем массив и объект
    deltas.append(ResponseToolCallDeltaEvent(
        type="response.tool_call.delta",
        response={"id": response_id},
        delta={"content": ["[{"]},
        sequence_number=-1,
    ))

    # Delta 2: type и call_id
    deltas.append(ResponseToolCallDeltaEvent(
        type="response.tool_call.delta",
        response={"id": response_id},
        delta={"content": [f'"type":"tool_call","call_id":"{tool_call_id}","name":"{tool_name}","arguments":"']},
        sequence_number=-1,
    ))

    # Delta 3-N: Куски аргументов (escaped)
    for chunk in arguments_chunks:
        escaped_chunk = chunk.replace('"', '\\"')
        deltas.append(ResponseToolCallDeltaEvent(
            type="response.tool_call.delta",
            response={"id": response_id},
            delta={"content": [escaped_chunk]},
            sequence_number=-1,
        ))

    # Delta N+1: Закрываем
    deltas.append(ResponseToolCallDeltaEvent(
        type="response.tool_call.delta",
        response={"id": response_id},
        delta={"content": ['"}]']},
        sequence_number=-1,
    ))

    return deltas
```

---

## Почему текущая реализация ломается

Давайте проследим, что делает Codex с текущими данными:

### Шаг 1: Получает delta seq 72
```json
"content": ["[{\"type\":\"tool_call\",...,\"arguments\":\"{\\\""}]"]
```

Парсит JSON → получает строку:
```
buffer = `[{"type":"tool_call",...,"arguments":"{""}]`
```

### Шаг 2: Получает delta seq 74
```json
"content": ["command"]
```

Добавляет:
```
buffer += "command"
// Результат: [{"type":"tool_call",...,"arguments":"{""}]command
```

**Это уже невалидный JSON!**

Массив закрылся на `]`, а потом идёт `command`.

### Шаг 3: Codex пытается парсить

```javascript
JSON.parse(buffer)
// Error: Unexpected token 'c' (command) after array end
```

Или если Codex пытается парсить сразу при получении delta:

```javascript
// Delta 72: content[0] после парсинга это строка с массивом
const delta1 = JSON.parse(delta.content[0])
// delta1 = [{"type":"tool_call",...}]  // Массив!

// Codex ожидает объект, получает массив
// Error: invalid type: array, expected object
```

---

## Что нужно исправить

### 1. Убрать квадратные скобки из обёртки

Вместо:
```python
content_str = json.dumps([tool_call_obj])  # "[{...}]"
```

Использовать:
```python
content_str = json.dumps(tool_call_obj)  # "{...}"
```

### 2. Отправлять ПОЛНЫЙ tool call одним delta

Не разбивать на части, пока не реализован правильный streaming.

### 3. Обновить тип в protocol.py

```python
# Было
delta: dict[str, list[ResponseToolCallDeltaContent]]

# Должно быть
delta: dict[str, list[str]]
```

---

## Тестовый сценарий

### До исправления (текущее поведение)

```bash
# Запрос к vLLM
curl -X POST http://192.168.228.43:8000/v1/responses \
  -d '{"model":"gpt-4o","input":"Run ls","tools":[...],"stream":true}'

# Получаем:
data: {"type":"response.tool_call.delta","delta":{"content":["[{\"type\":\"tool_call\",...}]"]},...}
# Следующие delta добавляют после закрывающей ]
# Результат: невалидный JSON при конкатенации
```

### После исправления

```bash
# Получаем:
data: {"type":"response.tool_call.delta","delta":{"content":["{\"type\":\"tool_call\",\"call_id\":\"...\",\"name\":\"shell\",\"arguments\":\"...\"}"]},...}
# Один delta с полным tool call
# Результат: валидный JSON объект
```

---

## Связь с Bug #4

Bug #4 был про `response.output_text.delta`:
- Проблема: отправляли объект `{"type":"text","text":"..."}`
- Решение: отправлять строку `"text content"`

Bug #5 про `response.tool_call.delta`:
- Проблема: отправляют массив `[{"type":"tool_call",...}]` + неправильный streaming
- Решение: отправлять объект (без массива) `{"type":"tool_call",...}` одним delta

**Общий паттерн**: vLLM добавляет лишние обёртки (объекты, массивы) вместо чистых строк/объектов согласно спецификации.

---

## Приоритет

🔴 **CRITICAL** - ломает streaming tool calls полностью.

Codex не может использовать vLLM для tool calling в streaming режиме из-за этого бага.

---

**Конец анализа**

Дата: 2025-11-25
Источник: Логи Codex
Статус: NOT FIXED
