# API_difference.md — отличие работы Codex с OpenAI Responses и другими API

## 1. Основные протоколы

Codex поддерживает два провода общения с LLM-провайдерами (см. `core/src/model_provider_info.rs:27-142`):

```
pub enum WireApi {
    Responses,       // POST /v1/responses (SSE, tool_outputs)
    Chat,            // POST /v1/chat/completions
}
```

Каждый провайдер в `model_providers` указывает `wire_api`. Для OpenAI и Azure — `responses`; для vLLM/Ollama прокси — чаще `chat`. Понять, какой режим активен, можно по коду (`core/src/client.rs:123-151`):

```rust
match self.provider.wire_api {
    WireApi::Responses => self.stream_responses(prompt).await,
    WireApi::Chat => {
        let response_stream = stream_chat_completions(...).await?;
        Ok(response_stream)
    }
}
```

Всё поведение дальше разделяется по двум веткам.

---

## 2. OpenAI Responses API

### Характеристики
- Endpoint: `/v1/responses`
- Запрос содержит `input`, `instructions`, `tools`, `parallel_tool_calls`, `reasoning`, `store`, `include`, `text`.
- Ответ — SSE поток с событиями `response.created`, `response.output_text.delta`, `response.tool_call.delta`, `response.completed`.
- Передача результатов инструмента: отдельный `POST /v1/responses/{id}/tool_outputs` (см. `api_tool_exchange_HOWTO.md`).
- Поддерживает `local_shell`, `web_search`, Reasoning, планировщик и т.д.

### Плюсы
1. Нативные tool calls и параллелизм.
2. Богатое событие `response.completed` (есть usage, reasoning tokens).
3. Возможность attach reasoning единиц (`include = ["reasoning.encrypted_content"]`).
4. В одном соединении можно запрашивать хранение (`store: true`) или кеширование (`prompt_cache_key`).

### Минусы
- Новый формат. Не все сторонние LLM реализуют `/responses`.
- Нужно указывать `store:true` для Azure.
- SSE обязательный: без поддержки EventSource невозможен стриминг.

### Место в коде
- Формирование payload: `core/src/client_common.rs` (`ResponsesApiRequest`).
- Триггер запуска: `stream_responses()` (`core/src/client.rs:187-284`).
- SSE парсер: `process_sse()` (`core/src/client.rs:528-720`).
- Инструменты добавляются через `create_tools_json_for_responses_api()` (`core/src/tools/spec.rs:669-706`).

---

## 3. Chat Completions API

### Характеристики
- Endpoint: `/v1/chat/completions` (классический OpenAI).
- Тело запроса — массив `messages` (system/user/assistant/tool), опционально `functions` (старый формат) но Codex сериализует инструменты в `messages`+`function_call` (см. `core/src/chat_completions.rs`).
- Ответ — тоже SSE, но события структурированы иначе: `delta`/`choices` вместо `response.*`.
- Tool calling поддерживается через `function_call`/`tool_calls` полям assistant сообщений.
- `tool_outputs` не существует: output инструмента встраивается в поток как `tool`-сообщение (`role="tool"`).

### Ограничения
1. Нет поля `reasoning`; приходится вручную приклеивать reasoning тексты к предыдущим assistant сообщениям.
2. Нельзя отправлять `store=false`/`include`/`prompt_cache_key`.
3. Встроенный `local_shell`/`web_search` типы отсутствуют — инструменты превращаются в обычные `function` записи.
4. Каждое tool использование превращается в pseudo- сообщение вида:
   ```json
   {"role":"assistant","tool_calls":[{"id":"call_x","type":"function","function":{"name":"exec_command","arguments":"{...}"}}]}
   ```
   После завершения Codex push’ит `{"role":"tool","tool_call_id":"call_x","content":"stdout..."}` обратно.

### Место в коде
- Основное: `stream_chat_completions()` (`core/src/chat_completions.rs:20-330`).
- Там видно, как Codex формирует `messages`, прикрепляет reasoning и поддерживает multimodal (изображения).
- Инструменты сериализуются через `create_tools_json_for_chat_completions_api()` (`core/src/tools/spec.rs:684-707`).

---

## 4. Примеры кода

### 4.1 Пример провайдера (OpenAI)

```toml
[model_providers.openai]
name = "OpenAI"
base_url = "https://api.openai.com/v1"
wire_api = "responses"
env_key = "OPENAI_API_KEY"
```

### 4.2 Пример провайдера (vLLM через Chat Completions)

```toml
[model_providers.local-vllm]
name = "Local vLLM"
base_url = "http://127.0.0.1:8001/v1"
wire_api = "chat"
http_headers = { Authorization = "Bearer local-key" }
stream_max_retries = 1
request_max_retries = 0
stream_idle_timeout_ms = 120000
```

### 4.3 Определение API в рантайме

```rust
// core/src/client.rs
match self.provider.wire_api {
    WireApi::Responses => self.stream_responses(prompt).await,
    WireApi::Chat => { ... }
}
```

Дополнительно, `ModelProviderInfo::get_full_url()` (`core/src/model_provider_info.rs:167-210`) формирует путь:

```rust
match self.wire_api {
    WireApi::Responses => format!("{base}/responses{qs}"),
    WireApi::Chat => format!("{base}/chat/completions{qs}"),
}
```

---

## 5. Когда выбирать что

| Ситуация | Рекомендованный API |
| -------- | ------------------- |
| OpenAI GPT-4.1/5 с полным tool calling | Responses. Доступны reasoning, web_search, local_shell. |
| Azure OpenAI Responses | Responses, но требуется `store=true` (см. `is_azure_responses_endpoint`). |
| vLLM с OpenAI совместимым `api_server` | Поддерживает оба; если реализован `/v1/responses`, можно переключить `wire_api` на `responses`. Иначе `chat`. |
| Ollama + прокси (например, `llama.cpp-openai`) | Chat. Эти прокси обычно повторяют старый chat completions протокол. |
| MCP-only режим (внешние инструменты важнее reasoning) | Любой. Разницы нет, поскольку MCP завязан на собственные HTTP-соединения. |

---

## 6. Взаимодействие с инструментами

| Возможность | Responses | Chat |
|-------------|-----------|------|
| `POST /responses/{id}/tool_outputs` | ✅ (обязательный шаг) | ❌ (нет отдельного endpoint) |
| Параллельные tool_calls | ✅ (`parallel_tool_calls = true`) | ✅ в новых OpenAI моделях, но сериализация идёт через массив `tool_calls`. |
| `local_shell` тип | ✅ | ❌ (Codex преобразует в обычную `function` запись) |
| `web_search` встроенный | ✅ | Частично (модель должна поддерживать `tool_calls`; но спец. тип отсутствует) |
| Reasoning разделен от текста | ✅ (`reasoning` поле, encrypted_content) | ❌ (пришивается вручную к assistant тексту) |
| Prompt caching / `store` | ✅ | ❌ |

---

## 7. Советы при добавлении нового провайдера

1. **Проверить поддержку** `/v1/responses`. Если нет — ставьте `wire_api = "chat"`.
2. **Настроить заголовки**. Responses требует `Accept: text/event-stream` + `conversation_id`. Chat — обычный SSE без доп. хедеров.
3. **Обработка ошибок**: ветка `stream_responses()` специально парсит JSON ошибки OpenAI и Azure. Для сторонних API (chat) ошибки приходят как `UnexpectedStatus` — тут стоит включить `log_level=debug`.
4. **Инструменты**. Они описываются одинаково (`core/src/tools/spec.rs`), но Responses получает `ToolSpec` напрямую, а Chat превращает их в `messages`+`functions`. Если провайдер не умеет tool calling (старые Ollama), инструменты просто игнорируются.

Теперь у вас есть цельный гайд по различиям и фрагменты кода, которые показывают, где Codex определяет тип API и как он переключает сетевую логику.
