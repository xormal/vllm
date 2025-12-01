# Анализ логов: Что происходит и что должно быть

## Ситуация

Codex правильно настроен на использование Responses API, но vLLM сервер отправляет неправильные SSE события, что приводит к пустым аргументам в tool calls.

---

## 1. Текущая конфигурация (✅ ПРАВИЛЬНО)

```
DEBUG Configuring session:
  model=openai/gpt-oss-120b
  wire_api: Responses
  base_url: Some("http://192.168.228.43:8000/v1")
  model_options: {"max_output_tokens": Number(8192), "temperature": Number(0.2), "top_p": Number(0.9)}
```

**Вывод**: Codex правильно настроен:
- ✅ `wire_api = Responses`
- ✅ URL: `http://192.168.228.43:8000/v1`
- ✅ Параметры модели корректны

---

## 2. HTTP запрос (✅ РАБОТАЕТ)

```
DEBUG Request completed
  method=POST
  url=http://192.168.228.43:8000/v1/responses  ← Правильный endpoint
  status=200 OK
  request_ids={"x-request-id": "resp_a1abbaab576c4b339e6e1984bd67aac8"}
  duration_ms=74
```

**Вывод**:
- ✅ Запрос отправлен на правильный endpoint `/v1/responses`
- ✅ Сервер отвечает 200 OK
- ✅ Response ID: `resp_a1abbaab576c4b339e6e1984bd67aac8`
- ✅ Соединение установлено за 74ms

---

## 3. SSE события (❌ НЕПРАВИЛЬНО)

### 3.1. Что отправляет vLLM СЕЙЧАС

#### Событие 1 (sequence_number: 72)

```json
{
  "type": "response.tool_call.delta",
  "response": {"id": "resp_a1abbaab576c4b339e6e1984bd67aac8"},
  "delta": {
    "content": [
      "[{\"type\":\"tool_call\",\"id\":\"call_6f1077cfc0f24e58b1990154ac1a4514\",\"call_id\":\"call_6f1077cfc0f24e58b1990154ac1a4514\",\"name\":\"shell\",\"arguments\":\"{\\\"\",\"status\":\"in_progress\"}]"
    ]
  },
  "sequence_number": 72
}
```

**Проблемы**:
1. ❌ **Тип события**: `response.tool_call.delta` - Codex **игнорирует** этот тип
2. ❌ **`delta.content`** - это **МАССИВ** `["..."]` вместо объекта
3. ❌ **Вложенность**: Внутри массива - JSON-строка с экранированием: `"[{\"type\":\"tool_call\"...}]"`
4. ❌ **Частичные аргументы**: `"arguments":"{\\\""}` - только `{"` (открывающая скобка и кавычка)

#### Событие 2 (sequence_number: 74)

```json
{
  "type": "response.tool_call.delta",
  "delta": {
    "content": [
      "[{\"type\":\"tool_call\",...,\"arguments\":\"{\\\"command\",\"status\":\"in_progress\"}]"
    ]
  },
  "sequence_number": 74
}
```

**Проблемы**:
- ❌ Еще одна порция аргументов: `"{\"command"` (добавлено слово "command" без закрывающей кавычки)

#### Событие 3 (sequence_number: 76)

```json
{
  "type": "response.tool_call.delta",
  "delta": {
    "content": [
      "[{...\"arguments\":\"{\\\"command\\\":[\\\"\",\"status\":\"in_progress\"}]"
    ]
  },
  "sequence_number": 76
}
```

**Проблемы**:
- ❌ Еще порция: `"{\"command\":[\""}` (добавлена открывающая квадратная скобка для массива)

#### Событие 4 (sequence_number: 78)

```json
{
  "type": "response.tool_call.delta",
  "delta": {
    "content": [
      "[{...\"arguments\":\"{\\\"command\\\":[\\\"bash\",\"status\":\"in_progress\"}]"
    ]
  },
  "sequence_number": 78
}
```

**Проблемы**:
- ❌ Еще порция: `"{\"command\":[\"bash"` (добавлен первый элемент массива "bash")

#### ... и так далее еще ~20 событий ...

---

### 3.2. Результат в Codex

```
DEBUG Output item item=Reasoning {
  id: "msg_e1a3d8683dcd483c8544a56b7c2df93b",
  summary: [],
  content: Some([ReasoningText {
    text: "We need to create AGENTS.md file... Let's list files."
  }])
}

DEBUG Output item item=FunctionCall {
  id: Some("fc_a91c3b62b3a14892bf54de0b207c5f24"),
  name: "shell",
  arguments: "",  ← ❌❌❌ ПУСТЫЕ АРГУМЕНТЫ!
  call_id: "call_6f1077cfc0f24e58b1990154ac1a4514"
}
```

**Проблема**: Codex видит tool call, но **аргументы пустые** (`arguments: ""`), поэтому не может выполнить команду!

**Почему**:
1. События `response.tool_call.delta` **игнорируются** Codex (строка 882-887 в `client.rs`)
2. Codex не накапливает частичные аргументы
3. Codex ожидает **ОДНО** событие `response.output_item.done` с **полными** аргументами

---

## 4. Что ДОЛЖНО быть

### 4.1. Правильная последовательность событий

#### Событие 1: `response.created`

```json
{
  "type": "response.created",
  "response": {
    "id": "resp_a1abbaab576c4b339e6e1984bd67aac8",
    "status": "in_progress"
  }
}
```

✅ Это событие уже отправляется (не показано в логах, но скорее всего есть).

---

#### Событие 2: `response.output_item.added` (начало reasoning)

```json
{
  "type": "response.output_item.added",
  "response": {"id": "resp_a1abbaab576c4b339e6e1984bd67aac8"},
  "item": {
    "type": "reasoning",
    "id": "msg_e1a3d8683dcd483c8544a56b7c2df93b",
    "content": [],
    "summary": []
  }
}
```

✅ Это работает (Codex видит reasoning item).

---

#### Событие 3: `response.reasoning_text.delta` (стрим reasoning)

```json
{
  "type": "response.reasoning_text.delta",
  "response": {"id": "resp_a1abbaab576c4b339e6e1984bd67aac8"},
  "delta": "We need to create AGENTS.md file..."
}
```

**ВАЖНО**: `delta` должна быть **СТРОКОЙ**, не объектом!

✅ Это работает (Codex видит reasoning text).

---

#### Событие 4: `response.output_item.done` (завершение reasoning)

```json
{
  "type": "response.output_item.done",
  "response": {"id": "resp_a1abbaab576c4b339e6e1984bd67aac8"},
  "item": {
    "type": "reasoning",
    "id": "msg_e1a3d8683dcd483c8544a56b7c2df93b",
    "content": [
      {
        "type": "reasoning_text",
        "text": "We need to create AGENTS.md file with content as per instructions. Should be concise 200-400 words. Use title \"Repository Guidelines\". Need to explore repo to see specifics: project name infinite-ttt, likely a Python tic-tac-toe? Let's list files."
      }
    ],
    "summary": []
  }
}
```

✅ Это работает (Codex получил reasoning).

---

#### Событие 5: `response.output_item.added` (начало tool call)

```json
{
  "type": "response.output_item.added",
  "response": {"id": "resp_a1abbaab576c4b339e6e1984bd67aac8"},
  "item": {
    "type": "function_call",
    "name": "shell",
    "arguments": "",
    "call_id": "call_6f1077cfc0f24e58b1990154ac1a4514"
  }
}
```

❓ Может присутствовать или нет (опционально).

---

#### Событие 6 (КЛЮЧЕВОЕ): `response.output_item.done` с ПОЛНЫМИ аргументами

```json
{
  "type": "response.output_item.done",
  "response": {"id": "resp_a1abbaab576c4b339e6e1984bd67aac8"},
  "item": {
    "type": "function_call",
    "name": "shell",
    "arguments": "{\"command\":[\"bash\",\"-lc\",\"ls\"]}",
    "call_id": "call_6f1077cfc0f24e58b1990154ac1a4514"
  }
}
```

**КРИТИЧНО**:
- ✅ Тип: `response.output_item.done` (НЕ `response.tool_call.delta`!)
- ✅ `item` - объект (НЕ массив!)
- ✅ `item.type` = `"function_call"` (НЕ `"tool_call"`)
- ✅ `item.arguments` - **ПОЛНАЯ JSON-строка**: `"{\"command\":[\"bash\",\"-lc\",\"ls\"]}"`

---

#### Событие 7: Ожидание tool_outputs

После отправки события 6, vLLM сервер должен **ОСТАНОВИТЬ стрим** и **ЖДАТЬ**:

```
POST /v1/responses/resp_a1abbaab576c4b339e6e1984bd67aac8/tool_outputs
Content-Type: application/json

{
  "tool_outputs": [
    {
      "call_id": "call_6f1077cfc0f24e58b1990154ac1a4514",
      "output": "total 64\ndrwxr-xr-x  5 user  staff   160 Nov 26 15:00 .\ndrwxr-xr-x  3 user  staff    96 Nov 25 10:00 ..\n-rw-r--r--  1 user  staff  1234 Nov 26 14:30 README.md\n..."
    }
  ]
}
```

---

#### Событие 8: Продолжение после tool_outputs

После получения tool_outputs, vLLM продолжает генерацию:

```json
{
  "type": "response.output_text.delta",
  "response": {"id": "resp_a1abbaab576c4b339e6e1984bd67aac8"},
  "delta": "Based on the file listing..."
}
```

---

#### Событие 9: `response.output_item.done` (финальное сообщение)

```json
{
  "type": "response.output_item.done",
  "response": {"id": "resp_a1abbaab576c4b339e6e1984bd67aac8"},
  "item": {
    "type": "message",
    "role": "assistant",
    "content": [
      {
        "type": "output_text",
        "text": "Based on the file listing, I'll create AGENTS.md..."
      }
    ]
  }
}
```

---

#### Событие 10: `response.completed`

```json
{
  "type": "response.completed",
  "response": {
    "id": "resp_a1abbaab576c4b339e6e1984bd67aac8",
    "usage": {
      "input_tokens": 150,
      "output_tokens": 75,
      "total_tokens": 225
    }
  }
}
```

---

## 5. Сравнение: СЕЙЧАС vs ДОЛЖНО БЫТЬ

### 5.1. Структура `delta.content`

#### ❌ СЕЙЧАС (НЕПРАВИЛЬНО):

```json
{
  "type": "response.tool_call.delta",
  "delta": {
    "content": [
      "[{\"type\":\"tool_call\",\"id\":\"call_...\",\"arguments\":\"{\\\"\"}]"
    ]
  }
}
```

**Проблемы**:
1. `delta.content` - **МАССИВ** со **строкой**
2. Строка содержит экранированный JSON
3. Частичные аргументы

#### ✅ ДОЛЖНО БЫТЬ (ПРАВИЛЬНО):

```json
{
  "type": "response.output_item.done",
  "item": {
    "type": "function_call",
    "name": "shell",
    "arguments": "{\"command\":[\"bash\",\"-lc\",\"ls\"]}",
    "call_id": "call_6f1077cfc0f24e58b1990154ac1a4514"
  }
}
```

**Исправлено**:
1. `item` - **ОБЪЕКТ** (не массив)
2. `item.type` = `"function_call"`
3. `item.arguments` - **ПОЛНАЯ** JSON-строка (не частичная)

---

### 5.2. Последовательность событий

#### ❌ СЕЙЧАС (НЕПРАВИЛЬНО):

```
1. response.created (✅)
2. response.reasoning_text.delta (✅)
3. response.output_item.done (reasoning) (✅)
4. response.tool_call.delta (seq 72) ❌ ИГНОРИРУЕТСЯ
5. response.tool_call.delta (seq 74) ❌ ИГНОРИРУЕТСЯ
6. response.tool_call.delta (seq 76) ❌ ИГНОРИРУЕТСЯ
7. response.tool_call.delta (seq 78) ❌ ИГНОРИРУЕТСЯ
... еще 20+ событий ...
N. response.tool_call.delta (seq X) ❌ ИГНОРИРУЕТСЯ
```

**Результат**: Codex видит `FunctionCall { arguments: "" }` - **ПУСТЫЕ АРГУМЕНТЫ**!

---

#### ✅ ДОЛЖНО БЫТЬ (ПРАВИЛЬНО):

```
1. response.created (✅)
2. response.reasoning_text.delta (✅)
3. response.output_item.done (reasoning) (✅)
4. response.output_item.added (function_call) (опционально)
5. response.output_item.done (function_call с ПОЛНЫМИ аргументами) ✅
6. [ЖДАТЬ tool_outputs]
7. response.output_text.delta (продолжение)
8. response.output_item.done (message)
9. response.completed
```

**Результат**: Codex видит `FunctionCall { arguments: "{\"command\":[\"bash\",\"-lc\",\"ls\"]}" }` - **ПОЛНЫЕ АРГУМЕНТЫ**!

---

## 6. Что нужно изменить в vLLM сервере

### 6.1. Убрать `response.tool_call.delta`

```python
# ❌ УДАЛИТЬ:
yield {
    "type": "response.tool_call.delta",
    "delta": {
        "content": [...]
    }
}
```

### 6.2. Накапливать аргументы

```python
# В начале функции генерации:
tool_call_accumulators = {}  # {call_id: {"name": str, "arguments": str}}

# При обнаружении tool call:
if is_tool_call_start:
    tool_call_accumulators[call_id] = {
        "name": "shell",
        "arguments": ""
    }

# При получении токенов аргументов:
if is_tool_call_argument:
    tool_call_accumulators[call_id]["arguments"] += token.text
    # НЕ отправлять response.tool_call.delta!

# При завершении tool call:
if is_tool_call_end:
    full_arguments = tool_call_accumulators[call_id]["arguments"]
    # Проверка валидности JSON:
    try:
        json.loads(full_arguments)
    except:
        # Исправить JSON если невалидный
        pass
```

### 6.3. Отправить `response.output_item.done`

```python
# При завершении tool call:
yield {
    "type": "response.output_item.done",
    "response": {"id": resp_id},
    "item": {
        "type": "function_call",
        "name": tool_call_accumulators[call_id]["name"],
        "arguments": tool_call_accumulators[call_id]["arguments"],  # ПОЛНЫЙ JSON
        "call_id": call_id
    }
}

del tool_call_accumulators[call_id]
```

### 6.4. Добавить endpoint для tool_outputs

```python
@app.post("/v1/responses/{response_id}/tool_outputs")
async def submit_tool_outputs(response_id: str, request: Request):
    body = await request.json()

    # Передать tool_outputs в ожидающий стрим
    if response_id in active_responses:
        active_responses[response_id]["future"].set_result(body["tool_outputs"])
        return {"status": "accepted"}

    return {"error": "Response not found"}, 404
```

### 6.5. Ждать tool_outputs в стриме

```python
async def generate_responses_stream(request, model):
    # ... генерация до tool call ...

    # Отправили tool call
    yield sse_event("response.output_item.done", {
        "item": {"type": "function_call", ...}
    })

    # ЖДАТЬ tool_outputs
    future = asyncio.Future()
    active_responses[resp_id] = {"future": future}
    tool_outputs = await future  # Блокирует до POST /tool_outputs

    # Продолжить генерацию с результатами
    for output in tool_outputs:
        # Добавить результат в промпт
        # Продолжить генерацию модели
        pass
```

---

## 7. Правильный формат `delta` для разных типов

### 7.1. Для текста (response.output_text.delta)

```json
{
  "type": "response.output_text.delta",
  "response": {"id": "resp_..."},
  "delta": "This is text content"
}
```

**`delta`** - это **СТРОКА** (не объект!)

---

### 7.2. Для reasoning (response.reasoning_text.delta)

```json
{
  "type": "response.reasoning_text.delta",
  "response": {"id": "resp_..."},
  "delta": "Step 1: analyze the code..."
}
```

**`delta`** - это **СТРОКА** (не объект!)

---

### 7.3. Для tool call (response.output_item.done)

```json
{
  "type": "response.output_item.done",
  "response": {"id": "resp_..."},
  "item": {
    "type": "function_call",
    "name": "shell",
    "arguments": "{\"command\":[\"ls\"]}",
    "call_id": "call_..."
  }
}
```

**`item`** - это **ОБЪЕКТ** (не массив!)

**`item.arguments`** - это **СТРОКА** с полным JSON (не частичная!)

---

## 8. Диагностика

### 8.1. Как проверить правильность

```bash
# Запрос к vLLM
curl -N -X POST http://192.168.228.43:8000/v1/responses \
  -H "Content-Type: application/json" \
  -d '{...}' 2>&1 | tee /tmp/vllm_sse.log

# Проверить события
grep "response.tool_call.delta" /tmp/vllm_sse.log
# Должно быть: ПУСТО (нет таких событий)

grep "response.output_item.done" /tmp/vllm_sse.log | grep "function_call"
# Должно быть: ОДНО событие с ПОЛНЫМИ аргументами
```

### 8.2. Проверка формата JSON

```python
import json

# Извлечь arguments из события
arguments = '{"command":["bash","-lc","ls"]}'

# Проверить валидность
try:
    parsed = json.loads(arguments)
    print("✅ Valid JSON:", parsed)
except json.JSONDecodeError as e:
    print("❌ Invalid JSON:", e)
```

---

## Итого

### Текущая ситуация:
- ❌ vLLM отправляет 20+ событий `response.tool_call.delta`
- ❌ Аргументы разбиты на части: `"{"`, потом `"command"`, потом `":[\"bash"`
- ❌ `delta.content` - массив со строкой, содержащей экранированный JSON
- ❌ Codex игнорирует все эти события
- ❌ Результат: `FunctionCall { arguments: "" }` - ПУСТЫЕ АРГУМЕНТЫ

### Что нужно исправить:
1. ✅ Накапливать аргументы в одну строку: `{"command":["bash","-lc","ls"]}`
2. ✅ Отправить ОДНО событие `response.output_item.done`
3. ✅ `item` должен быть объектом (не массивом)
4. ✅ `item.type` = `"function_call"` (не `"tool_call"`)
5. ✅ `item.arguments` - полная JSON-строка (не частичная)
6. ✅ Добавить endpoint `POST /v1/responses/{id}/tool_outputs`
7. ✅ Ждать tool_outputs и продолжить генерацию

### Результат после исправления:
- ✅ Codex видит: `FunctionCall { arguments: "{\"command\":[\"bash\",\"-lc\",\"ls\"]}" }`
- ✅ Tool call выполняется успешно
- ✅ Результаты возвращаются через tool_outputs
- ✅ Генерация продолжается с результатами
