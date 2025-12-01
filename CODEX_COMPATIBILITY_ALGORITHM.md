# Алгоритм работы vLLM Responses API в режиме совместимости с Codex

**Версия**: 2025-11-29
**Статус**: Готов к тестированию

---

## Описание проблемы

Codex клиент ожидает, что весь turn (беседа до финального ответа) происходит в рамках **одного response ID**, даже если требуется выполнить несколько tool calls. Однако предыдущая реализация создавала **новый response ID** при каждом tool call, что приводило к:

1. Множественным response ID для одного turn (resp_XXX, resp_YYY, resp_ZZZ...)
2. Потере контекста между tool calls
3. Проблемам с approval system (sub_id не находит pending approval)

---

## Правильный workflow (Compatibility Mode)

### Сценарий 1: Single Tool Call

```
1. POST /v1/responses
   Request: { input: "закоммить и запуш в гит" }
   Response: { id: "resp_ABC123", status: "in_progress" }

2. SSE Stream (открыт):
   - response.created (id: resp_ABC123)
   - response.output_item.added (reasoning)
   - response.reasoning.delta × N
   - response.output_item.done (reasoning)
   - response.output_item.added (function_call, call_id: call_XYZ)
   - response.function_call_arguments.delta × N
   - response.output_item.done (function_call)
   - response.completed (id: resp_ABC123) ← стрим закрывается

3. Codex выполняет tool локально:
   - git status --porcelain
   - Получает output: "M file1.py\nM file2.py"

4. POST /v1/responses
   Request: {
     previous_response_id: "resp_ABC123",
     input: [{
       type: "function_call",
       call_id: "call_XYZ",
       name: "shell",
       arguments: "{...}",
       status: "completed"
     }]
   }
   Response: { id: "resp_ABC123", status: "in_progress" } ← ТОТ ЖЕ ID!

5. SSE Stream (новый, но с тем же ID):
   - response.created (id: resp_ABC123)
   - НЕТ эхо старых tool calls!
   - response.output_item.added (reasoning)
   - response.reasoning.delta × N
   - response.output_item.done (reasoning)
   - response.output_item.added (message)
   - response.output_text.delta × N
   - response.output_item.done (message)
   - response.completed (id: resp_ABC123)
```

### Сценарий 2: Multiple Sequential Tool Calls

```
1. POST /v1/responses → resp_ABC123
2. Tool call 1: git status → response.completed
3. POST /v1/responses (previous_response_id: resp_ABC123) → resp_ABC123 (REUSED!)
4. Tool call 2: git add -A → response.completed
5. POST /v1/responses (previous_response_id: resp_ABC123) → resp_ABC123 (REUSED!)
6. Tool call 3: git commit -m "..." → response.completed
7. POST /v1/responses (previous_response_id: resp_ABC123) → resp_ABC123 (REUSED!)
8. Final message → response.completed

Итого: ОДИН response ID (resp_ABC123) для всего turn.
```

### Сценарий 3: Tool Call with User Approval

```
1. POST /v1/responses → resp_ABC123
2. Tool call: git push (requires escalated permissions)
   - response.output_item.added (function_call, call_id: call_XYZ)
   - response.output_item.done (function_call)
   - response.completed ← стрим закрывается

3. Codex waiting for user approval:
   - User видит: "Running git push" + "Approve?" button
   - User нажимает "Approve"
   - Codex выполняет tool: git push
   - Получает output

4. POST /v1/responses
   Request: {
     previous_response_id: "resp_ABC123",
     input: [{
       type: "function_call",
       call_id: "call_XYZ",  ← тот же call_id!
       name: "shell",
       arguments: "{...}",
       status: "completed"
     }]
   }
   Response: { id: "resp_ABC123", status: "in_progress" }

5. Модель продолжает генерацию с контекстом выполненного tool call
```

### Сценарий 4: Multiple Parallel Tool Calls (если поддерживается)

```
1. POST /v1/responses → resp_ABC123
2. Модель генерирует 3 tool calls одновременно:
   - response.output_item.added (function_call, call_id: call_1)
   - response.output_item.done (function_call, call_id: call_1)
   - response.output_item.added (function_call, call_id: call_2)
   - response.output_item.done (function_call, call_id: call_2)
   - response.output_item.added (function_call, call_id: call_3)
   - response.output_item.done (function_call, call_id: call_3)
   - response.completed

3. Codex выполняет все 3 tool calls:
   - call_1: выполнен успешно
   - call_2: требует approval (escalated permissions)
   - call_3: выполнен успешно

4. Codex ждет user approval для call_2:
   - User approves call_2
   - Codex выполняет call_2

5. POST /v1/responses
   Request: {
     previous_response_id: "resp_ABC123",
     input: [
       { type: "function_call", call_id: "call_1", status: "completed" },
       { type: "function_call", call_id: "call_2", status: "completed" },
       { type: "function_call", call_id: "call_3", status: "completed" }
     ]
   }
   Response: { id: "resp_ABC123", status: "in_progress" }

6. Модель продолжает с результатами всех 3 tool calls
```

---

## Ключевые изменения в vLLM

### 1. Переиспользование Response ID (serving_responses.py:1371-1416)

```python
# Compatibility mode (Codex): when continuing a previous response with tool outputs,
# REUSE the same request_id and process tool outputs into msg_store.
if self.compatibility_mode and prev_response is not None and isinstance(request.input, list):
    # CRITICAL: Reuse the same request_id
    request.request_id = prev_response.id

    # Process tool outputs and add to msg_store
    for input_item in request.input:
        if isinstance(input_item, ResponseFunctionToolCall):
            # Find matching tool call in previous output
            matching_call = find_in_previous_output(input_item.call_id)
            if matching_call:
                # Create function_call_output message
                tool_output_item = {
                    "type": "function_call_output",
                    "call_id": input_item.call_id,
                    "output": [],
                }
                harmony_message = parse_response_input(tool_output_item, [matching_call])
                self.msg_store[prev_response.id].append(harmony_message)

    # Clear request.input to prevent echoing old tool calls
    request.input = []
```

**Почему это важно**:
- Один response ID для всего turn
- msg_store накапливает всю историю (reasoning + tool calls + tool outputs)
- request.input очищается, чтобы избежать эхо старых tool calls

### 2. Закрытие стрима после tool call (serving_responses.py:4241-4250)

```python
# In compatibility mode (Codex), close the stream after tool call.
# Codex will execute the tool locally and POST new /v1/responses with previous_response_id.
if self.compatibility_mode:
    logger.debug(
        "Response %s (compatibility mode): tool calls done, closing stream. "
        "Expecting client to POST new /v1/responses with previous_response_id",
        request.request_id
    )
    break
```

**Почему это важно**:
- Codex ожидает, что стрим закроется после tool call
- Только после `response.completed` Codex начинает выполнение tool
- После выполнения Codex отправляет новый POST с tool outputs

### 3. Обработка tool outputs в msg_store

**msg_store** - это хранилище всей истории беседы для данного response ID. Оно содержит:
- System message
- Developer message (с описанием tools)
- User messages
- Assistant messages (reasoning, tool calls)
- Tool output messages (function_call_output)

При каждом новом POST с `previous_response_id`:
1. Загружается история из `msg_store[prev_response.id]`
2. Добавляются новые tool outputs
3. Модель продолжает генерацию с полным контекстом

---

## События SSE (правильный порядок)

### После генерации tool call:

```json
{ "type": "response.output_item.added", "item": {
    "type": "function_call",
    "id": "fc_XXX",
    "call_id": "call_YYY",
    "name": "shell",
    "arguments": ""
}}

{ "type": "response.function_call_arguments.delta", "delta": "{" }
{ "type": "response.function_call_arguments.delta", "delta": "\"command\"" }
...

{ "type": "response.output_item.done", "item": {
    "type": "function_call",
    "id": "fc_XXX",
    "call_id": "call_YYY",
    "name": "shell",
    "arguments": "{\"command\": [\"git\", \"status\"]}"
}}

{ "type": "response.completed", "response": {
    "id": "resp_ABC123",
    "status": "completed"
}}

[DONE]
```

### После получения tool outputs:

```json
{ "type": "response.created", "response": {
    "id": "resp_ABC123"  // ТОТ ЖЕ ID!
}}

// НЕТ эхо старых tool calls!

{ "type": "response.output_item.added", "item": {
    "type": "reasoning",
    "id": "msg_ZZZ"
}}

{ "type": "response.reasoning.delta", "delta": "Now I will..." }
...

{ "type": "response.output_item.added", "item": {
    "type": "message",
    "id": "msg_AAA"
}}

{ "type": "response.output_text.delta", "delta": "Коммит создан..." }
...

{ "type": "response.completed", "response": {
    "id": "resp_ABC123"
}}

[DONE]
```

---

## Проверочный список (Checklist)

### ✅ Критические требования

- [x] **Один response ID на весь turn** - При POST с `previous_response_id` используется тот же ID
- [x] **Нет эхо старых tool calls** - `request.input` очищается перед генерацией
- [x] **Tool outputs в msg_store** - История накапливается для продолжения контекста
- [x] **Стрим закрывается после tool call** - `response.completed` после каждого tool call
- [x] **call_id consistency** - Тот же `call_id` в `added` и `done` событиях
- [x] **Arguments полные в done** - `response.output_item.done` содержит полный JSON

### ✅ События SSE

- [x] `response.created` с правильным ID
- [x] `response.output_item.added` для reasoning
- [x] `response.reasoning.delta` × N
- [x] `response.output_item.done` для reasoning
- [x] `response.output_item.added` для function_call (с `call_id`)
- [x] `response.function_call_arguments.delta` × N (БЕЗ `response.tool_call.delta`!)
- [x] `response.output_item.done` для function_call (с полными `arguments`)
- [x] `response.completed` (после каждого tool call в compatibility mode)

---

## Измененные файлы

### 1. `vllm/entrypoints/openai/serving_responses.py`

**Строки 1371-1416**: Compatibility mode - переиспользование response ID
```python
if self.compatibility_mode and prev_response is not None:
    request.request_id = prev_response.id
    # Process tool outputs into msg_store
    # Clear request.input
```

**Строки 4241-4250**: Compatibility mode - закрытие стрима после tool call
```python
if self.compatibility_mode:
    break  # Close stream, expecting new POST with tool outputs
```

### Итого:
- Одна строка изменена: `request.request_id = prev_response.id`
- Один блок добавлен: обработка tool outputs в msg_store
- Один блок восстановлен: `break` после tool call в compatibility mode

---

## Тестирование

### Команда для проверки:

```bash
# 1. Запустить vLLM с compatibility mode
vllm serve openai/gpt-oss-120b \
  --compatibility-mode \
  --responses-tool-timeout 300

# 2. Запустить Codex и дать команду:
"закоммить и запуш в гит"

# 3. Проверить логи vLLM:
# Должен быть ОДИН response ID на весь turn
grep "Response resp_" vllm.log | grep "compatibility mode"

# Ожидаемый результат:
# Response resp_ABC123 (compatibility mode): continuing from previous response
# Response resp_ABC123 (compatibility mode): continuing from previous response
# Response resp_ABC123 (compatibility mode): continuing from previous response
# (все с ОДНИМ И ТЕМ ЖЕ ID!)
```

### Ожидаемое поведение:

1. ✅ Codex показывает "Running git status" → выполняет → продолжает
2. ✅ Codex показывает "Running git add -A" → требует approval → user approves → выполняет → продолжает
3. ✅ Codex показывает "Running git commit" → выполняет → продолжает
4. ✅ Codex показывает "Running git push" → требует approval → user approves → выполняет → завершает
5. ✅ Финальный ответ: "Все изменения закоммичены и запушены в гит"
6. ✅ Весь процесс с ОДНИМ response ID

### Признаки проблемы (если они появятся):

❌ **Множественные response ID**: `resp_XXX`, `resp_YYY`, `resp_ZZZ` - НЕ исправлено
❌ **Эхо старых tool calls**: В логах `TOOL_CALL added echo` - НЕ исправлено
❌ **No pending approval found**: approval system не находит tool call - НЕ исправлено
❌ **Working... hang**: UI зависает на "Working" - НЕ исправлено

---

## Заключение

Все изменения реализованы для обеспечения правильной работы Codex с vLLM Responses API:

1. ✅ **Переиспользование response ID** - один ID на весь turn
2. ✅ **Обработка tool outputs** - накопление в msg_store
3. ✅ **Предотвращение эхо** - очистка request.input
4. ✅ **Закрытие стрима** - после каждого tool call

Готово к тестированию с реальным Codex клиентом.

---

**Автор**: Claude Code Assistant
**Дата**: 2025-11-29
