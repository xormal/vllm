# Алгоритм работы vLLM Responses API в режиме совместимости с Codex (v2)

**Версия**: 2025-11-29 v2 (исправленная)
**Статус**: Готов к тестированию

---

## Благодарности

Благодарим команду Codex за детальный анализ в `ALGORITHM_VALIDATION_REPORT.md` и `ALGORITHM_CLARIFICATION.md`. Все исправления основаны на их обратной связи и изучении исходного кода Codex клиента.

---

## Ключевые исправления v2

### ❌ Что было неверно в v1:

1. Предполагалось, что Codex отправляет `previous_response_id` (НЕТ!)
2. Предполагалось переиспользование response ID (НЕ НУЖНО!)
3. Предполагалось хранение истории в `msg_store` на сервере (НЕВЕРНО!)
4. Предполагалось очищение `request.input` (НЕПРАВИЛЬНО!)

### ✅ Что верно (v2):

1. Codex отправляет `prompt_cache_key` (conversation ID)
2. Response ID может быть разным между запросами
3. **ВСЯ история передается в `request.input`** каждый раз
4. Сервер **НЕ должен эхоить** старые tool calls из `input` в SSE

---

## Правильный workflow (Codex)

### Сценарий 1: Single Tool Call

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
  "prompt_cache_key": "019ac0c8-7c4d-7bb1-a1d2-3f5e8a9b2c1d"  // ← Conversation ID!
  // ❌ НЕТ previous_response_id!
}
```

**Ответ SSE**:
```
response.created (id: resp_ABC123)
response.output_item.added (reasoning)
response.reasoning.delta × N
response.output_item.done (reasoning)
response.output_item.added (function_call, call_id: call_XYZ)
response.function_call_arguments.delta × N
response.output_item.done (function_call, arguments: "{\"command\":[\"git\",\"status\"]}")
response.completed (id: resp_ABC123)  ← Стрим закрывается
[DONE]
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

**Ответ SSE**:
```
response.created (id: resp_DEF456)  // ← НОВЫЙ response ID! (это нормально)

// ❌ СЕРВЕР НЕ ДОЛЖЕН ЭХОИТЬ старые tool calls из input!
// Только НОВЫЕ output items:

response.output_item.added (reasoning)
response.reasoning.delta × N
response.output_item.done (reasoning)
response.output_item.added (function_call, call_id: call_AAA, name: "shell")
response.function_call_arguments.delta × N
response.output_item.done (function_call, arguments: "{\"command\":[\"git\",\"add\",\"-A\"]}")
response.completed (id: resp_DEF456)
[DONE]
```

---

### Сценарий 2: Multiple Sequential Tool Calls

```
1. POST /v1/responses
   input: [user_message]
   → resp_ABC123
   → Tool call 1: git status
   → response.completed

2. POST /v1/responses
   input: [user_message, tool_call_1, tool_output_1]
   → resp_DEF456  (новый ID!)
   → Tool call 2: git add -A
   → response.completed

3. POST /v1/responses
   input: [user_message, tool_call_1, tool_output_1, tool_call_2, tool_output_2]
   → resp_GHI789  (новый ID!)
   → Tool call 3: git commit
   → response.completed

4. POST /v1/responses
   input: [user_message, tool_call_1, ..., tool_output_3]
   → resp_JKL012  (новый ID!)
   → Final message: "Все изменения закоммичены"
   → response.completed
```

**Итого**: РАЗНЫЕ response ID для каждого POST, но ВСЯ история в `input`.

---

### Сценарий 3: Tool Call with User Approval

```
1. POST /v1/responses → resp_ABC123
   → Tool call: git push (requires escalated permissions)
   → response.completed ← стрим закрывается

2. Codex ожидает user approval:
   - User видит: "Running git push" + "Approve?" button
   - User нажимает "Approve"
   - Codex выполняет tool: git push
   - Получает output

3. POST /v1/responses
   input: [
     {type: "message", ...},
     {type: "function_call", call_id: "call_XYZ", ...},  ← старый
     {type: "function_call_output", call_id: "call_XYZ", ...}  ← новый
   ]
   → resp_DEF456  (новый ID!)
   → Модель продолжает генерацию
```

**Ключевой момент**: `call_id` остается тем же между запросами, хотя response ID разные.

---

## Что vLLM ДОЛЖЕН делать (правильная логика)

### 1. Обработка `input`

```python
# Клиент отправил ALL HISTORY в request.input:
# - User messages
# - Old function_call items
# - Old function_call_output items

# vLLM должен:
# 1. Преобразовать input в формат модели (harmony messages)
#    через _construct_input_messages_with_harmony()
# 2. НЕ эхоить старые function_call в SSE стриме
# 3. Отправить только НОВЫЕ output items от модели
```

### 2. Отключение эхо в compatibility mode

```python
# serving_responses.py:4051-4054
# IMPORTANT: In compatibility mode (Codex), do NOT echo tool calls from input.
# Codex sends the entire history in request.input (user messages + old tool calls + tool outputs).
# Echoing them would duplicate tool calls in the SSE stream.
if not self.compatibility_mode and isinstance(request.input, list):
    # Echo logic только для standard mode
```

### 3. SSE события (правильная последовательность)

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

### 4. Закрытие стрима

```python
# serving_responses.py:4241-4250
# In compatibility mode (Codex), close the stream after tool call.
# Codex will execute the tool locally and POST new /v1/responses with tool output in input.
if self.compatibility_mode:
    logger.debug(
        "Response %s (compatibility mode): tool calls done, closing stream. "
        "Expecting client to POST new /v1/responses with tool outputs in input",
        request.request_id
    )
    break
```

---

## Ключевые параметры запроса

| Параметр | Что отправляет Codex | Назначение |
|----------|---------------------|------------|
| **model** | `"openai/gpt-oss-120b"` | Модель для генерации |
| **instructions** | `"You are Codex..."` | System prompt |
| **input** | `[message, function_call, function_call_output, ...]` | **ВСЯ ИСТОРИЯ** |
| **tools** | `[{type: "function", function: {...}}]` | Доступные инструменты |
| **tool_choice** | `"auto"` | Автоматический выбор tools |
| **parallel_tool_calls** | `true` | Разрешить параллельные tool calls |
| **stream** | `true` | SSE streaming |
| **prompt_cache_key** | `"019ac0c8-..."` | **Conversation ID** (не response ID!) |
| ~~previous_response_id~~ | ❌ **НЕТ** | Codex НЕ отправляет |

---

## Код исправлений в vLLM

### Единственное изменение (serving_responses.py:4051-4054)

```python
# БЫЛО:
if isinstance(request.input, list):
    for input_item in request.input:
        if isinstance(input_item, ResponseFunctionToolCall):
            # Echo tool call...

# СТАЛО:
if not self.compatibility_mode and isinstance(request.input, list):
    for input_item in request.input:
        if isinstance(input_item, ResponseFunctionToolCall):
            # Echo tool call...
```

**Что изменилось**:
- Добавлена проверка `not self.compatibility_mode`
- В compatibility mode эхо **отключено**
- Модель получает историю через `_construct_input_messages_with_harmony()`
- SSE отправляет только **НОВЫЕ** output items

---

## Проверочный список (Checklist)

### ✅ Критические требования

- [x] **НЕТ эхо старых tool calls** - `not self.compatibility_mode` в echo logic
- [x] **Стрим закрывается после tool call** - `break` в compatibility mode
- [x] **call_id consistency** - Тот же `call_id` в `added` и `done` событиях
- [x] **Arguments полные в done** - `response.output_item.done` содержит полный JSON
- [x] **История в input** - Вся история передается от клиента в `request.input`
- [x] **prompt_cache_key** - Используется conversation ID, а НЕ response ID

### ✅ События SSE

- [x] `response.created` с любым ID (может быть новый)
- [x] НЕТ эхо старых tool calls из input
- [x] `response.output_item.added` для НОВЫХ items (reasoning, tool calls)
- [x] `response.reasoning.delta` × N
- [x] `response.output_item.done` для reasoning
- [x] `response.output_item.added` для function_call (с `call_id`)
- [x] `response.function_call_arguments.delta` × N (БЕЗ `response.tool_call.delta`!)
- [x] `response.output_item.done` для function_call (с полными `arguments`)
- [x] `response.completed` (после каждого tool call в compatibility mode)

---

## Что НЕ НУЖНО делать

### ❌ Не переиспользовать response ID

```python
# ❌ НЕВЕРНО:
request.request_id = prev_response.id

# ✅ ВЕРНО:
# Ничего не делать, пусть будет новый ID
```

### ❌ Не хранить msg_store с привязкой к response ID

```python
# ❌ НЕВЕРНО:
self.msg_store[prev_response.id].append(harmony_message)

# ✅ ВЕРНО:
# Вся история приходит в request.input, хранилище не нужно
```

### ❌ Не очищать request.input

```python
# ❌ НЕВЕРНО:
request.input = []  # Это уничтожает историю!

# ✅ ВЕРНО:
# request.input содержит ВСЮ историю, не трогать
```

### ❌ Не использовать /tool_outputs endpoint

```python
# ❌ НЕВЕРНО:
POST /v1/responses/{id}/tool_outputs

# ✅ ВЕРНО:
# Codex НЕ использует этот endpoint
# Вместо этого отправляет tool outputs в input следующего POST /v1/responses
```

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

# 3. Проверить логи Codex:
# НЕ должно быть "Output item item=FunctionCall" для СТАРЫХ tool calls
# Должны быть только НОВЫЕ tool calls

# 4. Проверить логи vLLM:
# НЕ должно быть "TOOL_CALL added echo"
# Должно быть "TOOL_CALL added" только для НОВЫХ tool calls
```

### Ожидаемое поведение:

1. ✅ Codex показывает "Running git status" → выполняет → получает новый стрим с НОВЫМ tool call
2. ✅ Codex показывает "Running git add -A" → требует approval → user approves → выполняет → получает новый стрим
3. ✅ НЕТ дублирования tool calls в логах Codex
4. ✅ Каждый POST может иметь новый response ID (это нормально!)
5. ✅ `prompt_cache_key` остается тем же для всего разговора

### Признаки проблемы (если они появятся):

❌ **Эхо старых tool calls**: В логах Codex `Output item item=FunctionCall` для старых call_id
❌ **"TOOL_CALL added echo"** в логах vLLM - значит эхо не отключено
❌ **No pending approval found**: approval system не находит tool call
❌ **Working... hang**: UI зависает на "Working"

---

## Заключение

Единственное необходимое изменение для совместимости с Codex:

**Отключить эхо старых tool calls в compatibility mode** (1 строка кода)

```python
# serving_responses.py:4054
if not self.compatibility_mode and isinstance(request.input, list):
```

Все остальное уже правильно работает:
- История передается в `request.input` → обрабатывается через `_construct_input_messages_with_harmony()`
- Модель получает полный контекст
- Стрим закрывается после tool call
- Events генерируются правильно

Готово к тестированию с реальным Codex клиентом.

---

**Автор**: Claude Code Assistant
**Дата**: 2025-11-29 v2
**Благодарности**: Команде Codex за детальный анализ
