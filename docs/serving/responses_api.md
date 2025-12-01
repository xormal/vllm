# Responses API – Complete Reference

This guide documents vLLM's OpenAI-compatible Responses API implementation and
is intended for operators exposing `/v1/responses` directly to clients or
running compatibility tests.

## Endpoints

| Method | Path | Notes |
|--------|------|-------|
| `POST` | `/v1/responses` | Accepts `ResponsesRequest`. Supports streaming (`stream=true`), background execution (`background=true`, requires `store=true`). |
| `GET` | `/v1/responses/{id}` | Retrieve stored responses or resume a streaming session via `?stream=true&starting_after=<seq>`. |
| `POST` | `/v1/responses/{id}/cancel` | Cancels background jobs (`status in {"queued","in_progress"}`). |
| `POST` | `/v1/responses/{id}/tool_outputs` | Send tool call payloads (`tool_call_id`, `output[]`). |

## Request Model Highlights

- `input`: list of Harmony-formatted messages or plain string.
- `tools`: function definitions or builtin tool hints (Harmony).
- `service_tier`: `auto`, `default`, `flex`, `scale`, `priority`. Configure defaults with `--responses-default-service-tier` and allowlist via `--responses-allowed-service-tiers`.
- `store`: persist responses for later `GET`. Storage has TTL/quotas (`--responses-store-*` flags).
- `stream`: SSE when `true`. Non-streaming returns `ResponsesResponse`.
- `include`: supported options `code_interpreter_call.outputs`, `file_search_call.results`, `reasoning.encrypted_content`, `computer_call_output.output.image_url` (requires `--enable-computer-call`).
- Image tools: Harmony commands `image_generation.*`/`images.*` are enabled only when the server loads a multimodal checkpoint or you pass `--image-service-config` (see `ImageServices_HOWTO.md`). Otherwise the server rejects those tool calls with `response.error`.
- `prompt_cache_key`: mapped to `cache_salt` for prefix caching.

## Streaming Events

`_convert_stream_to_sse_events` emits named SSE events; client must accept
`text/event-stream`. Sequence numbers increase monotonically across reconnects.

- Core: `response.created`, `response.in_progress`, `response.completed`.
- Text: `response.output_item.added/done`, `response.output_text.delta/done`.
- Tools: `response.tool_call.delta`, `response.function_call_arguments.*`,
  `response.code_interpreter_call.*`, `response.web_search_call.*`.
- Reasoning: `response.reasoning.*`, `response.reasoning.summary.*`,
  `response.additional_context` (`reasoning.encrypted_content` include).
- System: `response.rate_limits.updated`, `response.error`, `response.ping`
  (keep-alive heartbeats, interval controlled by `--responses-ping-interval-seconds`).

Internally we buffer SSE payloads (~16 KB) and validate event types/sequence
numbers to prevent malformed streams.

## Tool Calling Workflow

1. Client sends `/v1/responses` with `tools=[...]` and `stream=true`.
2. Server emits `response.tool_call.delta` when the model needs external work.
3. Client executes the tool and POSTs to `/v1/responses/{id}/tool_outputs`.
4. Server resumes generation once all pending calls have results. Duplicate
   `tool_outputs` are rejected with `invalid_request_error`.

`ResponsesToolOutputsRequest` enforces size limits
(`--max-tool-output-bytes`). Pending tool calls expire if no output arrives
within `--responses-tool-timeout`.

## Rate Limits & Error Handling

- Set CLI flags or JSON config via `--rate-limits-config`.
- `429` responses include `Retry-After`. Rate limit usage updates with
  `response.rate_limits.updated`.
- All JSON/SSE errors include `error.type`, `error.message`. Requests with large
  bodies are guarded by `--max-request-body-bytes`,
  `--max-request-body-tokens`, `--max-stream-event-bytes`, and
  `--responses-stream-buffer-max-bytes`.

## Session Storage & Background Jobs

`ResponseSessionManager` tracks streaming sessions (TTL via
`--responses-session-ttl`). `GET /v1/responses/{id}?stream=true` replays stored
events. Background jobs use `store=true` and can be cancelled via
`POST /responses/{id}/cancel`.

## Compatibility Mode

Use `--responses-compatibility-mode` to reject vLLM-only fields (`request_id`,
`mm_processor_kwargs`, `priority`, `cache_salt`, `enable_response_messages`,
`previous_input_messages`) and restrict `include` to official OpenAI targets.
A header `X-Request-Id` mismatch with request body `request_id` results in
`invalid_request_error`.

## Operational Checklist

- Launch with `Accept: text/event-stream` aware proxies (nginx, envoy).
- Set `--responses-ping-interval-seconds` (default 15s) to keep connections
  alive through load balancers.
- When exposing to OpenAI clients, enable compatibility mode and keep `store`
  enabled for background flows.
