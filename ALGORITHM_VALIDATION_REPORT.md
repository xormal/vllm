# Отчет: Проверка алгоритма команды серверной части

**Дата**: 2025-11-29
**Проверяющий**: Claude Code Assistant
**Проверяемый документ**: `CODEX_COMPATIBILITY_ALGORITHM.md`
**Сравнение с**: Codex Rust клиент (codex-rs/core/)

---

## 📊 Общий вердикт

**Статус**: ⚠️ **ЧАСТИЧНО ВЕРНО** с критическими уточнениями

Команда серверной части **правильно понимает принцип работы** Codex, но есть **ошибка в ключевой детали реализации**.

---

## ✅ Что ПРАВИЛЬНО понято

### 1. ✅ Стрим закрывается после tool call

**Утверждение алгоритма** (строки 35, 64):
```
- response.completed (id: resp_ABC123) ← стрим закрывается
```

**Код клиента** (`core/src/client.rs:875-888`):
```rust
"response.completed" => {
    if let Some(resp_val) = event.response {
        match serde_json::from_value::<ResponseCompleted>(resp_val) {
            Ok(r) => {
                response_completed = Some(r);  // ← Сохраняет completed
            }
            // ...
        }
    };
}
```

**Проверка** (`core/src/client.rs:723-758`):
```rust
Ok(None) => {
    match response_completed {
        Some(ResponseCompleted { id: response_id, usage }) => {
            // ✅ Стрим закрыт, отправляем Completed event
            let event = ResponseEvent::Completed {
                response_id,
                token_usage: usage.map(Into::into),
            };
            let _ = tx_event.send(Ok(event)).await;
        }
        None => {
            // ❌ Стрим закрыт без response.completed - ошибка
            let error = CodexErr::Stream(
                "stream closed before response.completed".into(),
                None,
            );
            let _ = tx_event.send(Err(error)).await;
        }
    }
    return;  // ← Стрим завершен
}
```

**✅ ВЕРНО**: Клиент **ожидает**, что стрим закроется после `response.completed`.

---

### 2. ✅ Tool outputs отправляются в следующем запросе

**Утверждение алгоритма** (строки 44-51):
```python
4. POST /v1/responses
   Request: {
     previous_response_id: "resp_ABC123",
     input: [{
       type: "function_call",  # ← tool call + output
       call_id: "call_XYZ",
       status: "completed"
     }]
   }
```

**Код клиента** (`protocol/src/models.rs:25-28, 94-97`):
```rust
pub enum ResponseItem {
    // ...
    FunctionCallOutput {
        call_id: String,
        output: FunctionCallOutputPayload,
    },
    // ...
}
```

**Обработка** (`core/src/response_processing.rs:24-40`):
```rust
(
    ResponseItem::FunctionCall { .. },
    Some(ResponseInputItem::FunctionCallOutput { call_id, output }),
) => {
    items_to_record_in_conversation_history.push(item);  // ← FunctionCall
    items_to_record_in_conversation_history.push(ResponseItem::FunctionCallOutput {
        call_id,
        output,
    });  // ← FunctionCallOutput
}
```

**✅ ВЕРНО**: Клиент добавляет `FunctionCallOutput` в историю, которая отправляется в `input` следующего запроса.

---

### 3. ✅ Arguments полные в output_item.done

**Утверждение алгоритма** (строки 237-243):
```json
{ "type": "response.output_item.done", "item": {
    "type": "function_call",
    "call_id": "call_YYY",
    "name": "shell",
    "arguments": "{\"command\": [\"git\", \"status\"]}"  // ← ПОЛНЫЙ JSON
}}
```

**Код клиента** (`core/src/client.rs:802-812`):
```rust
"response.output_item.done" => {
    let Some(item_val) = event.item else { continue };
    let Ok(item) = serde_json::from_value::<ResponseItem>(item_val) else {
        debug!("failed to parse ResponseItem from output_item.done");
        continue;
    };

    let event = ResponseEvent::OutputItemDone(item);  // ← Передает item как есть
    if tx_event.send(Ok(event)).await.is_err() {
        return;
    }
}
```

**✅ ВЕРНО**: Клиент ожидает **полный** JSON в поле `arguments` события `output_item.done`.

---

### 4. ✅ Нет эхо старых tool calls

**Утверждение алгоритма** (строки 56, 260):
```
// НЕТ эхо старых tool calls!
```

**Обоснование**: Если сервер будет отправлять старые tool calls заново, клиент будет обрабатывать их как **новые** tool calls, что приведет к дублированию выполнения команд.

**✅ ВЕРНО**: Сервер **НЕ ДОЛЖЕН** эхо старых tool calls в следующем стриме.

---

## ❌ Что понято НЕВЕРНО (критическая ошибка!)

### ❌ Клиент НЕ отправляет `previous_response_id`!

**Утверждение алгоритма** (строки 44-52, 97-107, 135-144):
```python
POST /v1/responses
Request: {
  previous_response_id: "resp_ABC123",  # ❌ НЕВЕРНО!
  input: [...]
}
```

**Алгоритм предполагает** (строки 152-178):
```python
# CRITICAL: Reuse the same request_id
request.request_id = prev_response.id

# Process tool outputs and add to msg_store
for input_item in request.input:
    if isinstance(input_item, ResponseFunctionToolCall):
        # Find matching tool call in previous output
        matching_call = find_in_previous_output(input_item.call_id)
```

### ⚠️ Реальность: Клиент отправляет `prompt_cache_key`

**Код клиента** (`core/src/client_common.rs:266-284`):
```rust
#[derive(Debug, Serialize)]
pub(crate) struct ResponsesApiRequest<'a> {
    pub(crate) model: &'a str,
    pub(crate) instructions: &'a str,
    pub(crate) input: &'a Vec<ResponseItem>,  // ← История с tool outputs
    pub(crate) tools: &'a [serde_json::Value],
    pub(crate) tool_choice: &'static str,
    pub(crate) parallel_tool_calls: bool,
    pub(crate) reasoning: Option<Reasoning>,
    pub(crate) store: bool,
    pub(crate) stream: bool,
    pub(crate) include: Vec<String>,
    pub(crate) prompt_cache_key: Option<String>,  // ← ЗДЕСЬ!
    // ❌ НЕТ ПОЛЯ previous_response_id!
    pub(crate) text: Option<TextControls>,
}
```

**Реальный запрос** (`core/src/client.rs:241-254`):
```rust
let payload = ResponsesApiRequest {
    model: &self.config.model,
    instructions: &full_instructions,
    input: &input_with_instructions,  // ← Содержит ALL HISTORY!
    tools: &tools_json,
    tool_choice: "auto",
    parallel_tool_calls: prompt.parallel_tool_calls,
    reasoning,
    store: azure_workaround,
    stream: true,
    include,
    prompt_cache_key: Some(self.conversation_id.to_string()),  // ← Conversation ID
    text,
};
```

### 🔍 Ключевое различие

| Параметр | Алгоритм предполагает | Клиент отправляет |
|----------|----------------------|-------------------|
| **Идентификатор** | `previous_response_id: "resp_ABC123"` | `prompt_cache_key: "conv_UUID"` |
| **Тип** | Response ID (меняется каждый turn) | Conversation ID (один на весь разговор) |
| **Цель** | Найти предыдущий response в msg_store | Кэширование промпта (для оптимизации) |
| **История** | Должна извлекаться из msg_store | Передается полностью в `input` |

---

## 🎯 Правильная модель работы клиента

### Как ДЕЙСТВИТЕЛЬНО работает Codex

#### 1. **Первый запрос** (начало turn)

```http
POST /v1/responses
Content-Type: application/json

{
  "model": "openai/gpt-oss-120b",
  "instructions": "You are Codex...",
  "input": [
    {
      "type": "message",
      "role": "user",
      "content": [{"type": "input_text", "text": "закоммить и запуш в гит"}]
    }
  ],
  "tools": [...],
  "tool_choice": "auto",
  "parallel_tool_calls": true,
  "stream": true,
  "prompt_cache_key": "019ac0c8-7c4d-7bb1-a1d2-3f5e8a9b2c1d"  // ← Conversation ID
}
```

**Ответ**:
```
response.created (id: resp_ABC123)
response.output_item.added (reasoning)
...
response.output_item.done (reasoning)
response.output_item.added (function_call, call_id: call_XYZ, name: "shell")
response.output_item.done (function_call, arguments: "{\"command\":[\"git\",\"status\"]}")
response.completed (id: resp_ABC123)  ← Стрим закрывается
```

#### 2. **Клиент выполняет tool**

```bash
# Локально выполняет:
git status --porcelain
# Получает output:
M file1.py
M file2.py
```

#### 3. **Второй запрос** (продолжение turn)

```http
POST /v1/responses
Content-Type: application/json

{
  "model": "openai/gpt-oss-120b",
  "instructions": "You are Codex...",
  "input": [
    // ✅ ВСЯ ИСТОРИЯ передается заново!
    {
      "type": "message",
      "role": "user",
      "content": [{"type": "input_text", "text": "закоммить и запуш в гит"}]
    },
    {
      "type": "function_call",  // ← Старый tool call
      "id": "fc_ABC",
      "call_id": "call_XYZ",
      "name": "shell",
      "arguments": "{\"command\":[\"git\",\"status\"]}"
    },
    {
      "type": "function_call_output",  // ← Output от выполнения
      "call_id": "call_XYZ",
      "output": {
        "type": "text",
        "text": "M file1.py\nM file2.py"
      }
    }
  ],
  "tools": [...],
  "tool_choice": "auto",
  "parallel_tool_calls": true,
  "stream": true,
  "prompt_cache_key": "019ac0c8-7c4d-7bb1-a1d2-3f5e8a9b2c1d"  // ← ТОТ ЖЕ conversation ID
  // ❌ НЕТ previous_response_id!
}
```

**Ответ**:
```
response.created (id: resp_DEF456)  // ← НОВЫЙ response ID!
// ❌ СЕРВЕР НЕ ДОЛЖЕН ЭХОИТЬ старые tool calls из input!
response.output_item.added (reasoning)
...
response.output_item.done (reasoning)
response.output_item.added (function_call, call_id: call_AAA, name: "shell")
response.output_item.done (function_call, arguments: "{\"command\":[\"git\",\"add\",\"-A\"]}")
response.completed (id: resp_DEF456)
```

---

## 📝 Критические исправления алгоритма

### 1. Убрать `previous_response_id`

**БЫЛО** (строки 44-52):
```python
POST /v1/responses
Request: {
  previous_response_id: "resp_ABC123",  # ❌ Неверно!
  input: [...]
}
```

**ДОЛЖНО БЫТЬ**:
```python
POST /v1/responses
Request: {
  prompt_cache_key: "019ac0c8-...",  # ✅ Conversation ID
  input: [
    {type: "message", ...},  # ← История user message
    {type: "function_call", ...},  # ← Старый tool call
    {type: "function_call_output", ...}  # ← Tool output
  ]
}
```

### 2. Response ID может быть разным

**БЫЛО** (строки 52, 257):
```python
Response: { id: "resp_ABC123", status: "in_progress" } ← ТОТ ЖЕ ID!
```

**ДОЛЖНО БЫТЬ**:
```python
Response: { id: "resp_DEF456", status: "in_progress" } ← МОЖЕТ БЫТЬ НОВЫЙ!
```

**Пояснение**: Клиент **НЕ ТРЕБУЕТ** один и тот же response ID на весь turn. Каждый POST может возвращать новый ID. Клиент использует `prompt_cache_key` (conversation ID) для связи между запросами.

### 3. История передается в `input`, а не хранится в msg_store

**БЫЛО** (строки 172-177):
```python
# Process tool outputs and add to msg_store
for input_item in request.input:
    if isinstance(input_item, ResponseFunctionToolCall):
        # Find matching tool call in previous output
        matching_call = find_in_previous_output(input_item.call_id)
        harmony_message = parse_response_input(tool_output_item, [matching_call])
        self.msg_store[prev_response.id].append(harmony_message)

# Clear request.input to prevent echoing old tool calls
request.input = []
```

**ДОЛЖНО БЫТЬ**:
```python
# request.input СОДЕРЖИТ ВСЮ ИСТОРИЮ от клиента!
# НЕ НУЖНО искать в previous output, все уже есть в input.

# КРИТИЧНО: НЕ эхоить tool calls из input в стриме
# Отправлять только НОВЫЕ output items (reasoning, messages, tool calls)
```

---

## 🔧 Исправленная логика для vLLM

### Что vLLM ДОЛЖЕН делать

#### 1. Обработка `input`

```python
# Клиент отправил ALL HISTORY в request.input:
# - User messages
# - Old function_call items
# - Old function_call_output items

# vLLM должен:
# 1. Преобразовать input в формат модели (harmony messages)
# 2. НЕ эхоить старые function_call в SSE стриме
# 3. Отправить только НОВЫЕ output items
```

#### 2. SSE события (правильная последовательность)

```python
# После получения request.input с tool outputs:

# ✅ ОТПРАВИТЬ:
response.created (id: resp_NEW_ID)  # Может быть новый ID
response.output_item.added (reasoning)  # Новое reasoning
response.reasoning.delta × N
response.output_item.done (reasoning)

# Если модель хочет вызвать еще один tool:
response.output_item.added (function_call, call_id: call_NEW)  # ← НОВЫЙ tool call
response.function_call_arguments.delta × N
response.output_item.done (function_call)  # С полными arguments
response.completed

# ❌ НЕ ОТПРАВЛЯТЬ:
# - Старые function_call из input (НЕ эхоить!)
# - Старые function_call_output из input (НЕ эхоить!)
```

#### 3. Закрытие стрима

```python
# После любого tool call:
if has_function_call_in_output:
    yield response.completed
    break  # ← Закрыть стрим

# Клиент выполнит tool и отправит новый POST /v1/responses с tool output в input
```

---

## ✅ Что ОСТАЛОСЬ правильным

Несмотря на ошибку с `previous_response_id`, следующие пункты алгоритма **ВЕРНЫ**:

1. ✅ **Закрытие стрима после tool call** - клиент ожидает `response.completed`
2. ✅ **Tool outputs в следующем запросе** - клиент добавляет `FunctionCallOutput` в `input`
3. ✅ **Нет эхо старых tool calls** - сервер НЕ должен эхоить из `input`
4. ✅ **Arguments полные в done** - клиент ожидает полный JSON в `output_item.done`
5. ✅ **call_id consistency** - тот же `call_id` в `added` и `done`

---

## 📋 Checklist для команды серверной части

### ❌ Исправить в коде

- [ ] **Удалить логику `previous_response_id`** - клиент НЕ отправляет это поле
- [ ] **Удалить `request.request_id = prev_response.id`** - каждый POST может иметь новый ID
- [ ] **Удалить поиск в `previous output`** - вся история уже в `request.input`
- [ ] **НЕ очищать `request.input`** - это ВСЯ история от клиента

### ✅ Оставить как есть

- [x] **Закрытие стрима после tool call** - это правильно
- [x] **Не эхоить старые tool calls в SSE** - это правильно
- [x] **Отправлять полные arguments в done** - это правильно

---

## 🎯 Итоговое резюме

### Команда серверной части **правильно понимает**:

1. ✅ Стрим должен закрываться после tool call
2. ✅ Клиент отправляет tool outputs в следующем запросе
3. ✅ Сервер не должен эхоить старые tool calls
4. ✅ Arguments должны быть полными в `output_item.done`

### Команда серверной части **НЕ понимает**:

1. ❌ Клиент НЕ отправляет `previous_response_id`
2. ❌ Клиент отправляет `prompt_cache_key` (conversation ID)
3. ❌ Вся история передается в `input`, а не хранится в msg_store на сервере
4. ❌ Response ID может быть разным между запросами

### Что нужно исправить:

**В алгоритме** (`CODEX_COMPATIBILITY_ALGORITHM.md`):
- Заменить все упоминания `previous_response_id` на `prompt_cache_key`
- Убрать предположение о "переиспользовании response ID"
- Описать, что `input` содержит ВСЮ историю

**В коде** (`serving_responses.py`):
- Убрать `request.request_id = prev_response.id`
- Убрать поиск в `previous output`
- НЕ очищать `request.input`
- Просто преобразовать `input` в формат модели и НЕ эхоить в SSE

---

## 📚 Ссылки на код клиента

1. **Структура запроса**: `core/src/client_common.rs:266-284`
2. **Формирование запроса**: `core/src/client.rs:241-254`
3. **Обработка SSE событий**: `core/src/client.rs:783-917`
4. **Tool outputs**: `protocol/src/models.rs:25-28, 94-97`
5. **История разговора**: `core/src/response_processing.rs:24-40`

---

**Подготовил**: Claude Code Assistant
**Дата**: 2025-11-29
**Статус**: Готов к обсуждению с командой серверной части
