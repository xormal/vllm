# Уточнение: Codex НЕ использует `/tool_outputs` endpoint

**Дата**: 2025-11-29
**Вопрос**: Проверка алгоритма для Responses API, а не Chat API

---

## 🔍 Результат проверки

✅ **МОЙ АНАЛИЗ БЫЛ ВЕРНЫМ** - Codex использует Responses API, но **без** `/tool_outputs` endpoint.

---

## 📚 Два варианта Responses API

### Вариант 1: OpenAI официальная спецификация

**Endpoint для tool outputs**:
```
POST /v1/responses/{response_id}/tool_outputs
```

**Документация** (`OAI_API_spec.md:23`):
```
| POST  | `/v1/responses/{id}/tool_outputs` | Отправка результата инструментов. |
```

**Workflow**:
1. POST /v1/responses → response.created, tool_call → response.completed
2. Клиент выполняет tool
3. **POST /v1/responses/{id}/tool_outputs** ← Отдельный endpoint!
4. Сервер продолжает SSE stream

---

### Вариант 2: Codex реализация (ИСПОЛЬЗУЕТСЯ!)

**Endpoint для tool outputs**:
```
POST /v1/responses  (тот же endpoint)
```

**Код** (`core/tests/suite/unified_exec.rs:128-134`):
```rust
fn collect_tool_outputs(bodies: &[Value]) -> Result<HashMap<String, ParsedUnifiedExecOutput>> {
    let mut outputs = HashMap::new();
    for body in bodies {
        if let Some(items) = body.get("input").and_then(Value::as_array) {  // ← Ищет в input!
            for item in items {
                if item.get("type").and_then(Value::as_str) != Some("function_call_output") {
```

**Workflow**:
1. POST /v1/responses → response.created, tool_call → response.completed
2. Клиент выполняет tool
3. **POST /v1/responses** с tool outputs в `input` ← Тот же endpoint!
4. Сервер отвечает новым SSE stream

---

## ✅ Доказательства

### 1. Нет использования `/tool_outputs` в production коде

```bash
$ find codex-rs/core -name "*.rs" -exec grep -l "tool_outputs" {} \;
codex-rs/core/tests/suite/unified_exec.rs  # ← Только в ТЕСТАХ!
```

**В production коде (`core/src/*.rs`) - НИ ОДНОГО упоминания `/tool_outputs`!**

---

### 2. История передается в `input` каждый раз

**Код** (`core/src/codex.rs:1784-1787`):
```rust
let turn_input: Vec<ResponseItem> = {
    sess.record_conversation_items(&turn_context, &pending_input).await;
    sess.clone_history().await.get_history_for_prompt()  // ← ВСЯ ИСТОРИЯ!
};
```

**Код** (`core/src/client.rs:244`):
```rust
let payload = ResponsesApiRequest {
    model: &self.config.model,
    instructions: &full_instructions,
    input: &input_with_instructions,  // ← Содержит ВСЮ историю с tool outputs!
    // ...
};
```

---

### 3. Структура запроса БЕЗ `/tool_outputs`

**Определение** (`core/src/client_common.rs:266-284`):
```rust
pub(crate) struct ResponsesApiRequest<'a> {
    pub(crate) model: &'a str,
    pub(crate) instructions: &'a str,
    pub(crate) input: &'a Vec<ResponseItem>,  // ← ВСЯ история!
    pub(crate) tools: &'a [serde_json::Value],
    pub(crate) tool_choice: &'static str,
    pub(crate) parallel_tool_calls: bool,
    // ...
    pub(crate) prompt_cache_key: Option<String>,  // ← Conversation ID
    // ❌ НЕТ previous_response_id!
    // ❌ НЕТ tool_outputs!
}
```

---

### 4. Tool outputs в `input`

**Модель данных** (`protocol/src/models.rs:89-97`):
```rust
// NOTE: The input schema for `function_call_output` objects that clients send to the
// OpenAI /v1/responses endpoint is NOT the same shape as the objects the server returns on the
// SSE stream. When *sending* we must wrap the string output inside an object that includes a
// required `success` boolean.
FunctionCallOutput {
    call_id: String,
    output: FunctionCallOutputPayload,  // ← Это идет в input!
},
```

---

## 🎯 Почему команда серверной части ошиблась

### Предположение команды:

Они читали **официальную спецификацию OpenAI Responses API**, которая описывает:
```
POST /v1/responses/{id}/tool_outputs
```

И предположили, что Codex использует этот endpoint.

### Реальность Codex:

Codex **НЕ использует** `/tool_outputs` endpoint. Вместо этого:
- Все tool outputs отправляются в `input` следующего POST /v1/responses
- Используется `prompt_cache_key` для связи между запросами
- **Нет поля `previous_response_id`** в запросе

---

## 📝 Что это означает для алгоритма

### ❌ НЕВЕРНО в алгоритме команды:

```python
# Строки 44-52, 97-107 алгоритма
POST /v1/responses
Request: {
  previous_response_id: "resp_ABC123",  # ❌ НЕТ этого поля!
  input: [...]
}
```

### ✅ ВЕРНО должно быть:

```python
POST /v1/responses
Request: {
  prompt_cache_key: "019ac0c8-...",  # ✅ Conversation ID
  input: [
    {type: "message", role: "user", ...},  # История
    {type: "function_call", call_id: "call_XYZ", ...},  # Старый tool call
    {type: "function_call_output", call_id: "call_XYZ", output: {...}}  # Tool output
  ]
}
```

---

## 🔧 Что нужно исправить

### В алгоритме (`CODEX_COMPATIBILITY_ALGORITHM.md`):

1. ❌ Убрать все упоминания `previous_response_id`
2. ❌ Убрать логику переиспользования response ID
3. ❌ Убрать msg_store и поиск в previous output
4. ✅ Добавить, что вся история передается в `input`
5. ✅ Добавить, что используется `prompt_cache_key`

### В коде vLLM:

1. ❌ **НЕ НУЖЕН** endpoint `/v1/responses/{id}/tool_outputs`
2. ❌ **НЕ НУЖНО** переиспользовать response ID
3. ❌ **НЕ НУЖНО** хранить msg_store с привязкой к response ID
4. ✅ **НУЖНО** просто обработать `input` (вся история там!)
5. ✅ **НУЖНО** НЕ эхоить старые tool calls в SSE

---

## ✅ Заключение

**Мой анализ был ПРАВИЛЬНЫМ** для того, как Codex использует Responses API:

- ✅ Codex отправляет всю историю в `input`
- ✅ Codex использует `prompt_cache_key`, а не `previous_response_id`
- ✅ Codex НЕ использует `/tool_outputs` endpoint
- ✅ Response ID может быть разным между запросами

**Команда серверной части** читала официальную спецификацию OpenAI и предполагала другой workflow, но Codex реализован по-другому.

---

**Подготовил**: Claude Code Assistant
**Дата**: 2025-11-29
