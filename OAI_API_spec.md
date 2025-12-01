# OAI_API_spec.md — полный справочник OpenAI Responses API для Codex

Документ организован по разделам, чтобы по нему можно было восстановить **полностью совместимый** OpenAI Responses API. Каждая секция содержит принципы, структуры данных и работающий пример на Python.

1. [Протокол и эндпоинты](#протокол-и-эндпоинты)
2. [Формат запроса `/v1/responses`](#формат-запроса-v1responses)
3. [SSE-поток: события и usage](#sse-поток-события-и-usage)
4. [Tool calling и `/tool_outputs`](#tool-calling)
5. [Ошибки и лимиты](#ошибки-и-лимиты)
6. [Набор инструментов](#набор-инструментов)
7. [Azure-особенности](#azure)
8. [Python пример №1: минимальный FastAPI сервер](#пример-fastapi)
9. [Python пример №2: сервер поверх vLLM](#пример-vllm)
10. [Дополнительные ссылки и советы](#дополнительно)

---

## 1. Протокол и эндпоинты <a name="протокол-и-эндпоинты"></a>

| Метод | Путь | Назначение |
|-------|------|-----------|
| POST  | `/v1/responses` | Основной endpoint. Принимает JSON, отвечает SSE потоком. |
| POST  | `/v1/responses/{id}/tool_outputs` | Отправка результата инструментов. |

**Требования:** HTTPS, `Content-Type: application/json`, `Authorization: Bearer <token>`, `Accept: text/event-stream`. Codex использует HTTP/1.1 keep-alive.

---

## 2. Формат запроса `/v1/responses` <a name="формат-запроса-v1responses"></a>

```json
{
  "model": "gpt-4.1",
  "instructions": "You are Codex...",
  "input": [ ... ],
  "tools": [ ... ],
  "tool_choice": "auto",
  "parallel_tool_calls": true,
  "reasoning": {"effort":"medium"},
  "store": false,
  "stream": true,
  "include": ["reasoning.encrypted_content"],
  "prompt_cache_key": "019a...",
  "text": {"verbosity": "high"}
}
```

### Поля

| Поле | Описание |
|------|----------|
| `instructions` | Итоговый system prompt (см. `core/src/client_common.rs`). |
| `input` | История диалога в формате ResponseItem (user/assistant/messages). |
| `tools` | Массив инструментов (см. раздел 6). |
| `parallel_tool_calls` | Если `true`, модель может запрашивать несколько tool_calls за одно событие. |
| `text` | Настройки вывода (`verbosity`, `style`). Пока Codex использует только `verbosity`. |
| `include` | Дополнительные поля в ответе (reasoning). Можно игнорировать, если не поддерживается. |

---

## 3. SSE-поток: события и usage <a name="sse-поток-события-и-usage"></a>

Codex преобразует сигнал из SSE в `ResponseEvent` (`core/src/client_common.rs:197-217`). Ваш сервер должен уметь генерировать каждый тип. Ниже перечислены все события с кодом обмена.

### 3.1 `response.created` → `ResponseEvent::Created`

```sse
data: {"type":"response.created","response":{"id":"resp_123","status":"in_progress"}}
```
Отправляется сразу после приёма запроса.

### 3.2 `response.output_text.delta` → `ResponseEvent::OutputTextDelta(String)`

```sse
data: {
  "type": "response.output_text.delta",
  "response": {"id": "resp_123"},
  "delta": {
    "role": "assistant",
    "content": [
      {"type": "output_text", "text": "Привет, начнём с описания проекта."}
    ]
  }
}
```
Отправляется каждый раз, когда модель выдаёт новый фрагмент текста.

### 3.3 `response.tool_call.delta` → `ResponseEvent::OutputItemAdded/Done(ResponseItem)`

```sse
data: {
  "type": "response.tool_call.delta",
  "response": {"id": "resp_123"},
  "delta": {
    "content": [
      {
        "type": "tool_call",
        "id": "call_ls",
        "name": "exec_command",
        "arguments": "{\"cmd\":\"ls\"}"
      }
    ]
  }
}
```
Содержит один или несколько запросов к инструментам. После отправки сервер ждёт `POST /responses/{id}/tool_outputs`.

### 3.4 Reasoning события

Если вы вернёте encrypted reasoning (поле `include` в запросе), Codex ожидает:

- **`response.reasoning.delta`** → `ResponseEvent::ReasoningContentDelta(String)`
  ```sse
  data: {
    "type":"response.reasoning.delta",
    "response":{"id":"resp_123"},
    "delta":{"content":"Step 1: анализируем структуру репозитория..."}
  }
  ```
- **`response.reasoning.summary.delta`** → `ResponseEvent::ReasoningSummaryDelta(String)`
  ```sse
  data: {
    "type":"response.reasoning.summary.delta",
    "response":{"id":"resp_123"},
    "delta":{"summary":"Выполнил статический аудит и нашёл TODO в README"}
  }
  ```
- **`response.reasoning.summary.added`** → `ResponseEvent::ReasoningSummaryPartAdded`
  ```sse
  data: {
    "type":"response.reasoning.summary.added",
    "response":{"id":"resp_123"}
  }
  ```

Эти события опциональны и используются только при моделях с reasoning.

### 3.5 `response.output_item.done` / `response.output_item.added`

Когда Responses API возвращает полностью оформленный блок (например, финальное сообщение или tool output), он приходит отдельным `response.output_item.*`. Codex преобразует их в `ResponseEvent::OutputItemDone/OutputItemAdded(ResponseItem)`. Пример:

```sse
data: {
  "type": "response.output_item.done",
  "response": {"id": "resp_123"},
  "item": {
    "type": "message",
    "role": "assistant",
    "content": [{"type":"output_text","text": "Готово, вот README.md..."}]
  }
}
```

### 3.6 `response.error` → `ResponseEvent::OutputTextDelta + Completed`

```sse
data: {
  "type": "response.error",
  "response": {"id":"resp_123","status":"failed"},
  "error": {"type":"internal_error","message":"model crashed"}
}
```
После такого события Codex закрывает поток и уведомляет пользователя.

### 3.7 `response.completed` → `ResponseEvent::Completed`

```sse
data: {
  "type": "response.completed",
  "response": {"id": "resp_123", "status": "completed"},
  "usage": {
    "input_tokens": 4000,
    "input_tokens_details": {"cached_tokens": 500},
    "output_tokens": 900,
    "output_tokens_details": {"reasoning_tokens": 120},
    "total_tokens": 4900
  }
}
data: [DONE]
```

### 3.8 `response.additional_context` (необязательно)

Используется для передачи вспомогательной информации (например, `reasoning.encrypted_content`). Формат:
```sse
data: {
  "type": "response.additional_context",
  "response": {"id": "resp_123"},
  "context": {"reasoning.encrypted_content": "<base64>"}
}
```

### 3.9 Rate limits → `ResponseEvent::RateLimits`

Codex читает HTTP-заголовки `x-codex-*-used-percent` и преобразует их в событие `RateLimits`. Дополнительно можно отправлять отдельный SSE:
```sse
data: {
  "type": "response.rate_limits.updated",
  "response": {"id":"resp_123"},
  "limits": {"primary":{"used_percent":42.5,"window_minutes":60}}
}
```

### 3.10 Ping / keep-alive
Разрешено периодически отправлять `: ping` или любую пустую строку, чтобы соединение не простаивало.

---

## 4. Tool calling и `/tool_outputs` <a name="tool-calling"></a>

1. Сервер присылает `response.tool_call.delta` с массивом `content`.
2. Codex выполняет локальный инструмент.
3. Codex отправляет результат:
   ```json
   POST /v1/responses/{response_id}/tool_outputs
   {"tool_call_id":"call_ls","output":[{"type":"output_text","text":"stdout"}]}
   ```
4. Сервер продолжает опрашивать модель и возвращать SSE.

Если модель запрашивает несколько инструментов, Codex пришлёт несколько `tool_outputs`. Поток не заканчивается, пока все call_id не обработаны.

---

## 5. Ошибки и лимиты <a name="ошибки-и-лимиты"></a>

| Код | Что ожидать |
|-----|-------------|
| 429 | Верните `Retry-After` (секунды). Codex повторит запрос. |
| 401 | `{"error":{"type":"invalid_api_key","message":"..."}}`. Codex попробует обновить токен. |
| 5xx | Временная ошибка → Codex повторит до `request_max_retries`. |
| 400 | Текст ошибки попадёт пользователю. |

Специальные типы `error.type`: `usage_limit_reached`, `usage_not_included`, `quota_exceeded`.

---

## 6. Набор инструментов <a name="набор-инструментов"></a>

Codex объявляет инструменты из `core/src/tools/spec.rs`. Ваш сервер должен просто проксировать `tool_call` → `tool_outputs`:

| Имя | Тип | Назначение |
|-----|-----|-----------|
| `exec_command` | function | PTY-команда. |
| `write_stdin` | function | Пишет в stdin PTY-сессии. |
| `shell` | function | Single-shot shell без PTY. |
| `apply_patch` | function/freeform | Применение diff. |
| `read_file`, `grep_files`, `list_dir` | function | Файловые операции. |
| `view_image` | function | Прикрепление изображения. |
| `update_plan` | function | Обновление плана шагов. |
| `local_shell` | special | Responses API-тип (модель напрямую вызывает shell). |
| `web_search` | special | Веб-поиск. |

---

## 7. Azure-особенности <a name="azure"></a>

Если base_url Azure (`https://{resource}.openai.azure.com/...`):
- Принудительно `store: true`.
- `input` элементы должны иметь стабильные `id` (Codex использует `attach_item_ids`).
- Endpoint: `/openai/deployments/{model}/responses?api-version=2024-02-15-preview`.

---

## 8. Python пример №1: минимальный FastAPI сервер <a name="пример-fastapi"></a>

```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse
import asyncio, json, uuid

app = FastAPI()
pending_calls: dict[str, asyncio.Future] = {}

async def raw_llm_stream(body):
    # TODO: подключите свою модель (vLLM, transformers, llama.cpp)
    for token in ["Привет", {"type": "tool_call", "id": "call_ls", "name": "exec_command", "arguments": "{\\"cmd\\":\\"ls\\"}"}]:
        yield token

@app.post("/v1/responses")
async def responses(body: dict, request: Request):
    resp_id = str(uuid.uuid4())

    async def event_stream():
        yield {"event": "response.created", "data": {"response": {"id": resp_id, "status": "in_progress"}}}

        async for chunk in raw_llm_stream(body):
            if isinstance(chunk, str):
                yield {"event": "response.output_text.delta", "data": {"response": {"id": resp_id}, "delta": {"role": "assistant", "content": [{"type": "output_text", "text": chunk}]}}}
            elif chunk.get("type") == "tool_call":
                call_id = chunk["id"]
                fut = pending_calls[call_id] = asyncio.Future()
                yield {"event": "response.tool_call.delta", "data": {"response": {"id": resp_id}, "delta": {"content": [chunk]}}}
                tool_output = await fut
                yield tool_output_to_delta(tool_output, resp_id)

        usage = {"input_tokens": 1000, "output_tokens": 100, "total_tokens": 1100}
        yield {"event": "response.completed", "data": {"response": {"id": resp_id, "status": "completed"}, "usage": usage}}
        yield {"data": "[DONE]"}

    return EventSourceResponse(event_stream(), media_type="text/event-stream")

@app.post("/v1/responses/{resp_id}/tool_outputs")
async def tool_outputs(resp_id: str, payload: dict):
    call_id = payload["tool_call_id"]
    fut = pending_calls.pop(call_id, None)
    if fut:
        fut.set_result(payload)
    return JSONResponse({"status": "ok"})

def tool_output_to_delta(payload, resp_id):
    return {"event": "response.output_text.delta", "data": {"response": {"id": resp_id}, "delta": {"role": "assistant", "content": payload["output"]}}}
```

**Описание:**
- `raw_llm_stream` имитирует генерацию (замените на реальную модель).
- `pending_calls` хранит `Future` для каждого `tool_call_id`.
- `tool_output_to_delta` превращает `tool_outputs` обратно в SSE.

---

## 9. Python пример №2: обёртка над vLLM <a name="пример-vllm"></a>

```python
from fastapi import FastAPI
from sse_starlette.sse import EventSourceResponse
from vllm import AsyncLLMEngine
import asyncio, json, uuid

app = FastAPI()
engine = AsyncLLMEngine(model="meta-llama/Llama-3.1-70B-Instruct", trust_remote_code=True)
pending_calls: dict[str, asyncio.Future] = {}

async def vllm_stream(body):
    prompt = convert_input(body)
    async for result in engine.generate(prompt, stream=True):
        output = result.outputs[0]
        if output.stop_reason == "tool_call":
            yield {"type": "tool_call", "id": output.tool_id, "name": output.tool_name, "arguments": json.dumps(output.tool_args)}
        else:
            yield output.text

@app.post("/v1/responses")
async def responses(body: dict):
    resp_id = str(uuid.uuid4())

    async def event_stream():
        yield {"event": "response.created", "data": {"response": {"id": resp_id, "status": "in_progress"}}}
        async for chunk in vllm_stream(body):
            if isinstance(chunk, str):
                yield make_text_delta(resp_id, chunk)
            else:
                call_id = chunk["id"]
                fut = pending_calls[call_id] = asyncio.Future()
                yield make_tool_delta(resp_id, chunk)
                tool_output = await fut
                yield tool_output_to_delta(tool_output, resp_id)
        usage = estimate_usage(body)
        yield {"event": "response.completed", "data": {"response": {"id": resp_id, "status": "completed"}, "usage": usage}}
        yield {"data": "[DONE]"}

    return EventSourceResponse(event_stream(), media_type="text/event-stream")
```

Здесь `convert_input` превращает `body["input"]` в формат, понятный vLLM (обычно список `{role, content}`). Для tool calling надо обучить модель возвращать JSON (через system prompt).

---

## 10. Дополнительные ссылки и советы <a name="дополнительно"></a>

- `api_tool_exchange_HOWTO.md` — сеть и диаграммы TCP/TLS.
- `TOOL_USE_README.md` — полный список инструментов.
- `API_difference.md` — сравнение Responses vs Chat Completions.
- `core/src/client_common.rs` (`ResponseEvent`) — структура всех событий.

Следуя этому гайду, вы сможете построить API, которое Codex воспримет как OpenAI Responses, с поддержкой всех инструментов, reasoning, веб-поиска и параллельных tool_calls.
