# vLLM API Response Protocol - Complete Guide

## Table of Contents

1. [Overview](#overview)
2. [File Structure](#file-structure)
3. [Response Models](#response-models)
4. [API Endpoints](#api-endpoints)
5. [Response Protocols](#response-protocols)
6. [Streaming Protocol](#streaming-protocol)
7. [Responses API Architecture](#responses-api-architecture)
8. [Error Handling](#error-handling)
9. [Key Patterns](#key-patterns)
10. [Response Examples](#response-examples)
11. [Token Usage Tracking](#token-usage-tracking)

---

## Overview

vLLM implements an **OpenAI-compatible REST API** with multiple serving endpoints for different use cases. The API is built using **FastAPI** and supports both synchronous and streaming responses.

### Key Features:
- ✅ OpenAI API compatibility
- ✅ Multiple response formats (chat, completion, embeddings, etc.)
- ✅ Streaming support via Server-Sent Events (SSE)
- ✅ Advanced Responses API with tool calling and reasoning
- ✅ Comprehensive error handling
- ✅ Detailed token usage tracking

---

## File Structure

### Core API Files

```
vllm/entrypoints/
├── openai/
│   ├── api_server.py              # Main FastAPI server with all routes
│   ├── protocol.py                # All request/response model definitions (3299 lines)
│   ├── serving_engine.py          # Base OpenAI serving class
│   └── serving handlers:
│       ├── serving_responses.py   # NEW Responses API handler (2022 lines)
│       ├── serving_chat.py        # Chat completions handler
│       ├── serving_completion.py  # Text completions handler
│       ├── serving_embedding.py   # Embeddings handler
│       ├── serving_pooling.py     # Pooling/classification handler
│       ├── serving_score.py       # Scoring handler
│       ├── serving_tokenization.py
│       ├── serving_tokens.py
│       ├── serving_transcription.py
│       └── serving_classification.py
├── anthropic/
│   └── protocol.py                # Anthropic API compatibility
├── responses_utils.py             # Response utility functions
└── logger.py                      # Request/response logging
```

### Tool Parsers
```
vllm/entrypoints/openai/tool_parsers/
├── 40+ model-specific tool parsers
│   ├── granite_tool_parser.py
│   ├── mistral_tool_parser.py
│   ├── llama_tool_parser.py
│   └── ... (40+ more)
```

---

## Response Models

All response models inherit from `OpenAIBaseModel` which uses Pydantic v2 for validation.

### Base Model

```python
class OpenAIBaseModel(BaseModel):
    # OpenAI API does allow extra fields
    model_config = ConfigDict(extra="allow")
```

### 1. Chat Completion Response

**File**: `vllm/entrypoints/openai/protocol.py`

```python
class ChatCompletionResponse(OpenAIBaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl-{random_uuid()}")
    object: Literal["chat.completion"] = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: list[ChatCompletionResponseChoice]
    service_tier: Literal["auto", "default", "flex", "scale", "priority"] | None = None
    system_fingerprint: str | None = None
    usage: UsageInfo
    prompt_logprobs: list[dict[int, Logprob] | None] | None = None
    prompt_token_ids: list[int] | None = None
    kv_transfer_params: dict[str, Any] | None = None
```

**Choice Structure**:
```python
class ChatCompletionResponseChoice(OpenAIBaseModel):
    index: int
    message: ChatMessage
    logprobs: ChatCompletionLogProbs | None = None
    finish_reason: Literal["stop", "length", "tool_calls", "content_filter", "function_call"] | None = None
    stop_reason: int | str | None = None
```

### 2. Chat Completion Stream Response

```python
class ChatCompletionStreamResponse(OpenAIBaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl-{random_uuid()}")
    object: Literal["chat.completion.chunk"] = "chat.completion.chunk"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: list[ChatCompletionResponseStreamChoice]
    usage: UsageInfo | None = Field(default=None)
    prompt_token_ids: list[int] | None = None
```

**Stream Choice with Delta**:
```python
class DeltaMessage(OpenAIBaseModel):
    role: str | None = None
    content: str | None = None
    reasoning: str | None = None
    reasoning_content: str | None = None  # Deprecated: use reasoning
    tool_calls: list[DeltaToolCall] = Field(default_factory=list)
```

### 3. Text Completion Response

```python
class CompletionResponse(OpenAIBaseModel):
    id: str = Field(default_factory=lambda: f"cmpl-{random_uuid()}")
    object: Literal["text_completion"] = "text_completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: list[CompletionResponseChoice]
    service_tier: Literal["auto", "default", "flex", "scale", "priority"] | None = None
    system_fingerprint: str | None = None
    usage: UsageInfo
```

### 4. Embedding Response

```python
class EmbeddingResponse(OpenAIBaseModel):
    id: str = Field(default_factory=lambda: f"embd-{random_uuid()}")
    object: str = "list"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    data: list[EmbeddingResponseData]
    usage: UsageInfo
```

### 5. Responses API Response (NEW)

**File**: `vllm/entrypoints/openai/protocol.py`

```python
class ResponsesResponse(OpenAIBaseModel):
    id: str = Field(default_factory=lambda: f"resp_{random_uuid()}")
    created_at: int = Field(default_factory=lambda: int(time.time()))
    incomplete_details: IncompleteDetails | None = None
    instructions: str | None = None
    metadata: Metadata | None = None
    model: str
    object: Literal["response"] = "response"
    output: list[ResponseOutputItem]  # Can contain reasoning, messages, or tool calls
    parallel_tool_calls: bool
    temperature: float
    tool_choice: ToolChoice
    tools: list[Tool]
    top_p: float
    background: bool
    max_output_tokens: int
    max_tool_calls: int | None = None
    previous_response_id: str | None = None
    prompt: ResponsePrompt | None = None
    reasoning: Reasoning | None = None
    service_tier: Literal["auto", "default", "flex", "scale", "priority"]
    status: ResponseStatus  # "queued", "in_progress", "completed", "incomplete", "cancelled", "failed"
    text: ResponseTextConfig | None = None
    top_logprobs: int | None = None
    truncation: Literal["auto", "disabled"]
    usage: ResponseUsage | None = None
    user: str | None = None
```

**Response Output Item Types**:
```python
ResponseOutputItem: TypeAlias = Union[
    ResponseOutputMessage,      # Text messages
    ResponseReasoningItem,      # Reasoning output
    ResponseFunctionToolCall,   # Function calls
    ResponseCodeInterpreterToolCall,  # Code execution
    ResponseWebSearchToolCall   # Web search results
]
```

### 6. Error Response

```python
class ErrorInfo(OpenAIBaseModel):
    message: str
    type: str
    param: str | None = None
    code: int

class ErrorResponse(OpenAIBaseModel):
    error: ErrorInfo
```

---

## API Endpoints

### Chat Completions

**File**: `vllm/entrypoints/openai/api_server.py`

```python
@router.post("/v1/chat/completions")
async def create_chat_completion(
    request: ChatCompletionRequest,
    raw_request: Request
):
    handler = chat(raw_request)
    generator = await handler.create_chat_completion(request, raw_request)

    if isinstance(generator, ErrorResponse):
        return JSONResponse(content=generator.model_dump(), status_code=generator.error.code)
    elif isinstance(generator, ChatCompletionResponse):
        return JSONResponse(content=generator.model_dump())
    else:  # streaming
        return StreamingResponse(content=generator, media_type="text/event-stream")
```

**Returns**:
- `ChatCompletionResponse` (non-streaming)
- `StreamingResponse` with `text/event-stream` (streaming)
- `ErrorResponse` (on error)

### Text Completions

```python
@router.post("/v1/completions")
async def create_completion(
    request: CompletionRequest,
    raw_request: Request
):
    # Similar pattern to chat completions
```

**Returns**:
- `CompletionResponse` (non-streaming)
- `StreamingResponse` with `text/event-stream` (streaming)
- `ErrorResponse` (on error)

### Responses API (NEW)

```python
@router.post("/v1/responses")
async def create_responses(
    request: ResponsesRequest,
    raw_request: Request
):
    handler = responses(raw_request)

    if request.background:
        # Background processing mode
        response = await handler.create_responses_background(request, raw_request)
        return JSONResponse(content=response.model_dump())

    generator = await handler.create_responses(request, raw_request)

    if isinstance(generator, ErrorResponse):
        return JSONResponse(content=generator.model_dump(), status_code=generator.error.code)
    elif isinstance(generator, ResponsesResponse):
        return JSONResponse(content=generator.model_dump())
    else:  # streaming
        return StreamingResponse(content=generator, media_type="text/event-stream")
```

**Returns**:
- `ResponsesResponse` with `status="queued"` (background mode)
- `ResponsesResponse` (synchronous, non-streaming)
- `StreamingResponse` with SSE events (streaming)
- `ErrorResponse` (on error)

### Responses Retrieval

```python
@router.get("/v1/responses/{response_id}")
async def retrieve_responses(
    response_id: str,
    stream: bool | None = False
):
    # Retrieve stored response by ID
```

```python
@router.post("/v1/responses/{response_id}/cancel")
async def cancel_responses(response_id: str):
    # Cancel background response processing
```

### Stateful Response Sessions

`ResponseSessionManager` keeps every streaming/background response in-memory so
clients can reconnect or resume polling:

- `POST /v1/responses` with `stream=true` spawns a background producer task and
  registers a `ResponseSession` (id = `request_id`). Events are appended to a
  deque; reconnecting with `GET /v1/responses/{id}?stream=true` replays the deque
  via `responses_background_stream_generator`.
- Sessions have TTL and `--responses-max-active-sessions` limits; idle entries
  are evicted automatically, cancelling their background tasks.
- `handle_stream_disconnect` is called when the SSE connection drops, ensuring
  the session is cleaned up immediately.

Operational tips:

```bash
# keep sessions for 10 minutes, cap at 2k concurrent
python -m vllm.entrypoints.openai.api_server \
  --responses-session-ttl 600 \
  --responses-max-active-sessions 2000
```

If you rely on reconnection, use `store=true` so completed responses are persisted;
otherwise the session disappears once `response.completed` is emitted.

### Response Storage (`store=true`)

- Enable storage per request with `store=true`; background (`background=true`)
  requires it.
- Storage controls:
  - `--disable-responses-store` disables persistence entirely.
  - `--responses-store-ttl` (seconds) expires completed responses lazily.
  - `--responses-store-max-entries` + `--responses-store-max-bytes` protect RAM.
- Stored responses are returned by `GET /v1/responses/{id}` even after the live
  session is gone, and `_update_stored_response_status` keeps status fields
  (`queued`, `in_progress`, `completed`, `failed`, `cancelled`) in sync.

- Original request items are available through
  `GET /v1/responses/{id}/input_items`. Pagination mirrors OpenAI:
  `limit` (1–100, default 20), `order=asc|desc` (default `desc`), and `after`
  to continue from a specific `item_id`. Only stored responses expose input
  items; requests with `store=false` return `404`.

```bash
curl "http://localhost:8000/v1/responses/$ID/input_items?limit=10&order=asc" \
  -H "Authorization: Bearer dev" | jq .
```

- Unsupported `include` filters on `input_items` return `invalid_request_error`
  so clients know that the extra payloads (e.g., image URLs) require a
  multimodal deployment.

Use `RESP_LIMITS_HOWTO.md` for sizing guidance.

### Responses Tool Outputs

Use this endpoint to resume a streaming Responses session after your tool code
has finished executing. The router lives in
`vllm/entrypoints/openai/api_server.py:1020+` and accepts the OpenAI payload:

```http
POST /v1/responses/{response_id}/tool_outputs
Content-Type: application/json

{
  "tool_call_id": "call_1",
  "output": [
    {"type": "output_text", "text": "Forecast: 22°C, sunny"}
  ]
}
```

On success the server returns `{"id": "<response_id>", "status": "in_progress"}`
and the SSE stream continues where it paused. Validation happens inside
`OpenAIServingResponses.submit_tool_outputs`:

- Rejects oversized bodies (`--max-tool-output-bytes` or `RESPONSES_MAX_TOOL_OUTPUT_BYTES`).
- Ensures the referenced `tool_call_id` is pending and that the response is
  currently waiting for tool outputs.
- Stores the tool output inside the Harmony context and wakes the generator via
  the per-session `resume_event`.

You can test the full workflow by:

```bash
# 1) Create a streaming response with tools
curl -N -H "Accept: text/event-stream" \
  -d @request.json http://localhost:8000/v1/responses > stream.log &

# 2) Submit tool results once you parse call_id from stream.log
curl -X POST http://localhost:8000/v1/responses/resp_xxx/tool_outputs \
  -H "Content-Type: application/json" \
  -d '{"tool_call_id":"call_1","output":[{"type":"output_text","text":"OK"}]}'
```

If the SSE connection drops or the tool output never arrives within
`--responses-tool-timeout` seconds, the server logs the timeout and emits a
`response.error` event.

### Prompt Cache Key

OpenAI requests can include `prompt_cache_key` to pin cache hits even if the
prompt changes slightly. vLLM maps this to its internal prefix-cache salt:

```json
{
  "model": "gpt-4o",
  "input": "Summarize README.md",
  "prompt_cache_key": "repo_docs_v1"
}
```

- The field lives on `ResponsesRequest` (`protocol.py:372+`). Empty strings are
  rejected.
- `_apply_prompt_cache_key` copies the key into `cache_salt` unless the caller
  already set `cache_salt` manually (in that case the salt wins and we log a warning).
- Works for both streaming and synchronous/background responses because
  `create_responses` applies the mapping before scheduling the generation.

**Tips**

- Use a stable key (UUID/slug) per logical prompt to maximize cache reuse.
- Combine with `--enable-prefix-caching` / `VLLM_PREFIX_CACHE_MAX_NUM` settings
  when launching the server.
- If you need to bypass the key on a single request, provide your own
  `cache_salt` – it takes precedence.

### Compatibility Mode

The server now enables Responses compatibility by default so the wire format
matches the OpenAI spec without extra flags. To opt out (e.g., during internal
experiments that rely on vLLM-only fields), pass
`--responses-compatibility-mode=false` when launching:

```bash
python -m vllm.entrypoints.openai.api_server \
  --model <MODEL> \
  --responses-compatibility-mode=false
```

While enabled:

- Extra parameters like `request_id`, `mm_processor_kwargs`, `priority`,
  `cache_salt`, `enable_response_messages`, and `previous_input_messages` are
  rejected with `invalid_request_error`.
- `include` is limited to the OpenAI-documented targets:
  `code_interpreter_call.outputs`, `file_search_call.results`,
  `reasoning.encrypted_content`.
- Streamed reasoning and tool events are auto-shimmed to the string-based
  payloads expected by older OpenAI SDKs, even though the internal generator
  uses the latest event types.

Leave compatibility mode enabled for OpenAI SDKs and compliance runs; only turn
it off if you explicitly need legacy request fields or event formats.

### Include Parameter Options

Set `include` on the request to opt-in to richer payloads:

| Include Target | Behavior | Notes |
|----------------|----------|-------|
| `code_interpreter_call.outputs` | Stream stdout/stderr results inside `response.code_interpreter_call.completed`. | Enabled by default when requested. |
| `file_search_call.results` | Emit chunks summarizing search hits. | Requires Harmony context with file search tool. |
| `computer_call_output.output.image_url` | Surface links to generated screenshots. | Requires launching server with `--enable-computer-call`. |
| `web_search_call.action.sources` | Adds a `response.additional_context` payload describing the sources returned by the web search tool. | Currently forwards whatever `sources` the tool returns (often empty when running without a browser backend). |
| `message.input_image.image_url` | Emits a `response.additional_context` payload enumerating the `input_image` URLs present in the request. | Best-effort: entries are mirrored from the raw request even when the serving model is text-only. |
| `message.output_text.logprobs` | Includes log probability deltas in streaming output and the final response. | Unsupported for Harmony models because they do not expose per-token logprobs. |
| `reasoning.encrypted_content` | Adds encrypted reasoning blobs so stateless conversations can reuse reasoning tokens. | Requires configuring `--reasoning-encryption-key`. |

Implementation lives in `serving_responses.py:_request_includes` plus the Harmony
streaming loops; unsupported targets fall back to silently omitting the payload.

> **Codex compatibility note:** Our internal Codex client is pinned to the
> spring‑2024 Responses API. To keep it working we intentionally emit
> `response.tool_call.delta` as the original string-based payload
> (`delta.content=["{\\"type\\":…}"]`) and we currently allow only
> `tool_choice="auto"` for Harmony models. Do not switch to the new
> `tool_call_arguments_delta` schema or expose explicit tool_choice routing
> until Codex is updated. See `BUG_5_TOOL_CALL_DELTA_FORMAT.md` for details.

Built-in tools such as web search, file search, and image generation raise the
OpenAI streaming events (`response.web_search_call.*`,
`response.file_search_call.*`, `response.image_generation_call.*`) whenever the
model emits those tool calls. Even when the demo ToolServer does not execute the
tool, the SSE sequence mirrors OpenAI so SDKs continue to function. Commands
`image_generation.*` / `images.*` additionally require either a multimodal
checkpoint or the new `--image-service-config` flag (see `ImageServices_HOWTO.md`);
otherwise the server stops the request with `response.error` to prevent
accidental image calls.
### Conversations API

The server now exposes the canonical OpenAI Conversations endpoints so clients
can persist conversation state between `/v1/responses` calls:

- `POST /v1/conversations` – create a conversation container with optional
  metadata/title and seed items.
- `GET|POST|DELETE /v1/conversations/{conversation_id}` – retrieve/update/delete
  metadata (status, title, metadata).
- `GET|POST|DELETE /v1/conversations/{conversation_id}/items` – list, append, or
  remove individual conversation items (messages, tool outputs, etc.).

Conversations are stored in-memory via `ConversationStore` (see
`vllm/entrypoints/openai/conversation_store.py`) with a default capacity of 1 000
entries. Requests mirror the OpenAI schema; responses contain `conversation`
objects and `conversation.item` records with timestamps/metadata.

### Service Tier Controls

- Client field `service_tier` accepts `auto`, `default`, `flex`, `scale`, or `priority`.
- `--responses-default-service-tier` controls what `"auto"` maps to (default: `auto`).
- `--responses-allowed-service-tiers` sets the server-side allowlist; requests outside
  this set receive `invalid_request_error`.

The normalized tier is echoed in the final `ResponsesResponse.service_tier`, so downstream
systems can audit which tier actually ran.

### Embeddings

```python
@router.post("/v1/embeddings")
async def create_embedding(
    request: EmbeddingRequest,
    raw_request: Request
):
    # Returns EmbeddingResponse or EmbeddingBytesResponse
```

---

## Response Protocols

### 1. REST API Protocol

- **Framework**: FastAPI + Uvicorn
- **Base URL**: Configurable (default: `http://localhost:8000`)
- **Content Types**:
  - `application/json` - for non-streaming responses
  - `text/event-stream` - for streaming responses

### 2. OpenAI Compatibility

All responses are fully compatible with the OpenAI Python client:

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="EMPTY"
)

# Works seamlessly with vLLM
response = client.chat.completions.create(
    model="meta-llama/Llama-2-7b-chat-hf",
    messages=[{"role": "user", "content": "Hello!"}]
)
```

### 3. HTTP Headers Compatibility

- `x-request-id`: echoed from the request ID (or generated for SSE) so clients
  can correlate logs.
- `OpenAI-Organization` / `OpenAI-Version`: copied from inbound headers or the
  server defaults (`--default-openai-organization`, `--default-openai-version`).
- Rate limit headers (`x-ratelimit-limit-*`, `x-ratelimit-remaining-*`) are
  produced by `OpenAIServingResponses.build_rate_limit_headers` when tracking is
  enabled.
- Azure-specific fields (`x-ms-region`, `x-ms-request-id`,
  `api-supported-versions`) mirror OpenAI’s Azure API.

All routes call `_apply_standard_response_headers` (`api_server.py:684-710`), so
JSON responses, SSE streams, cancels, and tool_outputs share the same header
surface.

### 3. Response Status Codes

- `200 OK` - Success
- `400 Bad Request` - Invalid request parameters
- `404 Not Found` - Resource not found (e.g., response ID)
- `500 Internal Server Error` - Server error

---

## Streaming Protocol

### Server-Sent Events (SSE)

**Format**:
```
data: <json_object>\n\n
```

For named events:
```
event: <event_name>
data: <json_object>\n\n
```

### Chat Completion Streaming

**File**: `vllm/entrypoints/openai/serving_chat.py`

```python
async def chat_completion_stream_generator(
    # Yields ChatCompletionStreamResponse objects
) -> AsyncGenerator[str, None]:
    for response in responses:
        yield f"data: {response.model_dump_json()}\n\n"
    yield "data: [DONE]\n\n"
```

**Example Stream**:
```
data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1699564000,"model":"llama-2-7b","choices":[{"index":0,"delta":{"role":"assistant","content":""},"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1699564000,"model":"llama-2-7b","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1699564000,"model":"llama-2-7b","choices":[{"index":0,"delta":{"content":" world"},"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1699564000,"model":"llama-2-7b","choices":[{"index":0,"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":10,"completion_tokens":3,"total_tokens":13}}

data: [DONE]
```

### Responses API Streaming Events

**File**: `vllm/entrypoints/openai/serving_responses.py`

The Responses API uses **named SSE events** with a sequence number:

```python
async def _convert_stream_to_sse_events(
    generator: AsyncGenerator[StreamingResponsesResponse, None],
) -> AsyncGenerator[str, None]:
    sequence_number = 0
    async for event in generator:
        event_dict = event.model_dump(exclude_none=True)
        event_dict["sequence_number"] = sequence_number
        event_type = event_dict.get("type", "unknown")

        yield f"event: {event_type}\n"
        yield f"data: {json.dumps(event_dict)}\n\n"

        sequence_number += 1
    yield "data: [DONE]\n\n"
```

### Complete List of Responses API Events

| Event Type | Description |
|------------|-------------|
| `response.created` | Response object initialized |
| `response.in_progress` | Processing started |
| `response.output_item.added` | New output item added |
| `response.output_item.done` | Output item completed |
| `response.content_part.added` | Text/code content started |
| `response.content_part.done` | Text/code content finished |
| `response.output_text.delta` | Text chunk (streaming) |
| `response.output_text.done` | Text generation completed |
| `response.reasoning.delta` | Reasoning chunk (OpenAI format) |
| `response.reasoning.done` | Reasoning completed |
| `response.reasoning.summary.added` | Summary stream initialized |
| `response.reasoning.summary.delta` | Reasoning summary chunk |
| `response.reasoning_part.added` | Reasoning item started |
| `response.reasoning_part.done` | Reasoning item completed |
| `response.additional_context` | Encrypted reasoning + metadata |
| `response.rate_limits.updated` | Rate limit usage snapshot |
| `response.tool_call.delta` | Streaming function-call arguments |
| `response.error` | Streaming failure notification |
| `response.function_call_arguments.delta` | Function args chunk |
| `response.function_call_arguments.done` | Function args complete |
| `response.code_interpreter_call.in_progress` | Code execution started |
| `response.code_interpreter_call_code.delta` | Code chunk |
| `response.code_interpreter_call_code.done` | Code complete |
| `response.code_interpreter_call.interpreting` | Code executing |
| `response.code_interpreter_call.completed` | Code execution done |
| `response.web_search_call.in_progress` | Web search started |
| `response.web_search_call.searching` | Web search running |
| `response.web_search_call.completed` | Web search done |
| `response.ping` | Keep-alive heartbeat (vLLM extension) |
| `response.completed` | Response fully completed |
| `[DONE]` | End-of-stream marker (no event name) |

> **Compatibility:** Use the `--legacy-reasoning-events` flag (or `legacy_reasoning_events=true`
> in configs) if you still need the older `response.reasoning_text.*` events for clients that
> have not migrated to OpenAI's `response.reasoning.*` schema.

**Example Responses API Stream**:
```
event: response.created
data: {"type":"response.created","sequence_number":0,"response":{"id":"resp_123","status":"in_progress",...}}

event: response.output_item.added
data: {"type":"response.output_item.added","sequence_number":1,"output_index":0,"item":{"type":"message","id":"msg_abc"}}

event: response.output_text.delta
data: {"type":"response.output_text.delta","sequence_number":2,"delta":"Hello","item_id":"msg_abc","content_index":0}

### Tool Call Delta Example

When Harmony chooses a tool, you receive `response.tool_call.delta` events with
incremental JSON arguments:

```
event: response.tool_call.delta
data: {
  "type": "response.tool_call.delta",
  "sequence_number": 5,
  "response": {"id": "resp_123"},
  "delta": {
    "content": [
      {
        "type": "tool_call",
        "id": "fc_a1b2",
        "call_id": "call_1",
        "name": "get_weather",
        "arguments": "{\"city\":\"Tokyo\"}"
      }
    ]
  }
}
```

Use the emitted `call_id` when posting tool outputs. The server buffers these
deltas per session (see `ResponseStreamSession.register_tool_call`) and resumes
generation only after `POST /responses/{id}/tool_outputs` supplies matching
outputs.

### Ping / Keep-Alive

When responses run longer than a few seconds, vLLM sends periodic `response.ping`
events to prevent idle proxies from closing connections. Configure the cadence via
`--responses-ping-interval-seconds` (default 15s, set to `0` to disable).

Example chunk:

```
event: response.ping
data: {"type":"response.ping","sequence_number":42,"timestamp":1715875000.12,"response":{}}
```

Clients should ignore these events but keep the stream open.

event: response.output_text.delta
data: {"type":"response.output_text.delta","sequence_number":3,"delta":" world","item_id":"msg_abc","content_index":0}

event: response.output_text.done
data: {"type":"response.output_text.done","sequence_number":4,"text":"Hello world","item_id":"msg_abc","content_index":0}

event: response.output_item.done
data: {"type":"response.output_item.done","sequence_number":5,"output_index":0,"item":{"type":"message","id":"msg_abc","status":"completed",...}}

event: response.completed
data: {"type":"response.completed","sequence_number":6,"response":{"id":"resp_123","status":"completed","usage":{...}}}
```

---

## Responses API Architecture

### Handler Class

**File**: `vllm/entrypoints/openai/serving_responses.py`

```python
class OpenAIServingResponses(OpenAIServing):
    def __init__(self, ...):
        # Storage for background processing
        self.response_store: dict[str, ResponsesResponse] = {}
        self.msg_store: dict[str, list[ChatCompletionMessageParam]] = {}
        self.event_store: dict[str, tuple[deque[StreamingResponsesResponse], asyncio.Event]] = {}
```

### Response Status States

```python
ResponseStatus = Literal[
    "queued",       # Request waiting to start (background mode)
    "in_progress",  # Currently being processed
    "completed",    # Finished successfully
    "incomplete",   # Max tokens reached
    "cancelled",    # User cancelled
    "failed"        # Error occurred
]
```

### Output Item Types

#### 1. Response Output Message
```python
class ResponseOutputMessage(OpenAIBaseModel):
    id: str
    content: list[ResponseOutputText | ResponseOutputRefusal]
    role: Literal["assistant"]
    status: Literal["in_progress", "completed", "incomplete"]
    type: Literal["message"] = "message"
```

#### 2. Response Reasoning Item
```python
class ResponseReasoningItem(OpenAIBaseModel):
    id: str
    content: list[ResponseReasoningContent]
    role: Literal["assistant"]
    status: Literal["in_progress", "completed"]
    type: Literal["reasoning"] = "reasoning"
```

#### 3. Response Function Tool Call
```python
class ResponseFunctionToolCall(OpenAIBaseModel):
    id: str
    call_id: str
    function: ResponseFunction
    status: Literal["in_progress", "completed"]
    type: Literal["function"] = "function"
```

#### 4. Response Code Interpreter Tool Call
```python
class ResponseCodeInterpreterToolCall(OpenAIBaseModel):
    id: str
    call_id: str
    code_interpreter: ResponseCodeInterpreter
    status: Literal["in_progress", "completed", "failed"]
    type: Literal["code_interpreter"] = "code_interpreter"
```

#### 5. Response Web Search Tool Call
```python
class ResponseWebSearchToolCall(OpenAIBaseModel):
    id: str
    call_id: str
    web_search: ResponseWebSearch
    status: Literal["in_progress", "completed", "failed"]
    type: Literal["web_search"] = "web_search"
```

### Processing Flow

#### Full (Non-Streaming) Generator

**File**: `vllm/entrypoints/openai/serving_responses.py:1449`

```python
async def responses_full_generator(
    request: ResponsesRequest,
    sampling_params: SamplingParams,
    result_generator: AsyncIterator[ConversationContext],
    context: ConversationContext,
    model_name: str,
    tokenizer: AnyTokenizer,
    request_metadata: RequestResponseMetadata,
) -> ResponsesResponse | ErrorResponse:
    # 1. Process all generation tokens
    async for conversation_context in result_generator:
        context = conversation_context

    # 2. Parse output items (messages, reasoning, tool calls)
    output = self._make_response_output_items(
        request, context.final_output, tokenizer
    )

    # 3. Build usage info with detailed token counts
    usage = ResponseUsage(
        input_tokens=num_prompt_tokens,
        output_tokens=num_generated_tokens,
        total_tokens=num_prompt_tokens + num_generated_tokens,
        input_tokens_details=InputTokensDetails(...),
        output_tokens_details=OutputTokensDetails(...)
    )

    # 4. Return final response
    return ResponsesResponse.from_request(
        request, sampling_params, model_name, created_time,
        output=output, status="completed", usage=usage
    )
```

#### Streaming Generator

**File**: `vllm/entrypoints/openai/serving_responses.py:1577`

```python
async def responses_stream_generator(
    # ... parameters
) -> AsyncGenerator[StreamingResponsesResponse, None]:
    # 1. Yield ResponseCreatedEvent with initial response
    yield ResponseCreatedEvent(response=ResponsesResponse(...))

    # 2. Yield ResponseInProgressEvent
    yield ResponseInProgressEvent(response_id=response_id)

    # 3. Process generation and yield events
    if harmony_mode:
        async for event in _process_harmony_streaming_events(...):
            yield event
    else:
        async for event in _process_simple_streaming_events(...):
            yield event

    # 4. Yield ResponseCompletedEvent with final response
    yield ResponseCompletedEvent(response=final_response)
```

### Building Response Output Items

**File**: `vllm/entrypoints/openai/serving_responses.py:903`

```python
def _make_response_output_items(
    self,
    request: ResponsesRequest,
    final_output: CompletionOutput,
    tokenizer: AnyTokenizer,
) -> list[ResponseOutputItem]:
    content = final_output.text
    reasoning = None

    # Parse reasoning if enabled
    if self.reasoning_parser:
        reasoning, content = self.reasoning_parser.extract_reasoning(content)

    # Parse tool calls
    tool_calls, content = self._parse_tool_calls_from_content(
        content, request, tokenizer
    )

    outputs = []

    # Add reasoning item
    if reasoning:
        outputs.append(ResponseReasoningItem(
            id=f"reasoning_{random_uuid()}",
            content=[ResponseReasoningContent(
                reasoning=reasoning,
                type="reasoning"
            )],
            role="assistant",
            status="completed",
            type="reasoning"
        ))

    # Add message item
    if content:
        outputs.append(ResponseOutputMessage(
            id=f"msg_{random_uuid()}",
            content=[ResponseOutputText(
                text=content,
                type="output_text",
                annotations=[]
            )],
            role="assistant",
            status="completed",
            type="message"
        ))

    # Add tool call items
    for tool_call in tool_calls:
        outputs.append(ResponseFunctionToolCall(
            id=f"call_{random_uuid()}",
            call_id=tool_call["id"],
            function=ResponseFunction(
                arguments=tool_call["function"]["arguments"],
                name=tool_call["function"]["name"]
            ),
            status="completed",
            type="function"
        ))

    return outputs
```

---

## Error Handling

### Creating Error Responses

**File**: `vllm/entrypoints/openai/serving_engine.py`

```python
def create_error_response(
    self,
    message: str,
    err_type: str = "invalid_request_error",
    status_code: HTTPStatus = HTTPStatus.BAD_REQUEST,
) -> ErrorResponse:
    return ErrorResponse(
        error=ErrorInfo(
            message=message,
            type=err_type,
            param=None,
            code=status_code.value
        )
    )
```

### Error Types

| Error Type | Status Code | Description |
|------------|-------------|-------------|
| `invalid_request_error` | 400 | Invalid request parameters |
| `not_found_error` | 404 | Resource not found |
| `InternalServerError` | 500 | Server error |
| `ValidationError` | 400 | Request validation failed |

### Error Response in Routes

```python
if isinstance(generator, ErrorResponse):
    return JSONResponse(
        content=generator.model_dump(),
        status_code=generator.error.code
    )
```

### Streaming Error Response

```python
def create_streaming_error_response(
    self,
    message: str,
    err_type: str = "invalid_request_error",
    status_code: HTTPStatus = HTTPStatus.BAD_REQUEST,
) -> str:
    error_response = self.create_error_response(message, err_type, status_code)
    return f"data: {error_response.model_dump_json()}\n\n"
```

### Retry-After Headers

When an `ErrorResponse` carries HTTP 429 (`rate_limit_error`), the server adds a
`Retry-After` header (default 1 second or `error.retry_after`). This logic lives
in `_maybe_add_retry_after_header` and runs for both JSON and streaming errors,
so OpenAI SDKs know when to retry.

---

## Key Patterns

### 1. Handler Pattern (Dependency Injection)

**File**: `vllm/entrypoints/openai/api_server.py`

```python
# Handler is injected via FastAPI dependency
@router.post("/v1/chat/completions")
async def create_chat_completion(
    request: ChatCompletionRequest,
    raw_request: Request
):
    handler = chat(raw_request)  # Dependency injection
    generator = await handler.create_chat_completion(request, raw_request)

    # Pattern: Check type and return appropriate response
    if isinstance(generator, ErrorResponse):
        return JSONResponse(content=generator.model_dump(), status_code=generator.error.code)
    elif isinstance(generator, ChatCompletionResponse):
        return JSONResponse(content=generator.model_dump())
    else:  # AsyncGenerator
        return StreamingResponse(content=generator, media_type="text/event-stream")
```

### 2. Response Caching (Responses API)

**File**: `vllm/entrypoints/openai/serving_responses.py`

```python
class OpenAIServingResponses:
    def __init__(self, ...):
        # In-memory storage for background responses
        self.response_store: dict[str, ResponsesResponse] = {}
        self.msg_store: dict[str, list[ChatCompletionMessageParam]] = {}
        self.event_store: dict[str, tuple[deque[StreamingResponsesResponse], asyncio.Event]] = {}

    def _store_response(self, response_id: str, response: ResponsesResponse):
        self.response_store[response_id] = response

    def _get_response(self, response_id: str) -> ResponsesResponse | None:
        return self.response_store.get(response_id)
```

### 3. Serialization Pattern

**File**: `vllm/entrypoints/openai/protocol.py`

```python
@field_serializer("output_messages", when_used="json")
def serialize_output_messages(self, msgs, _info):
    return serialize_messages(msgs)

def serialize_messages(msgs):
    serialized = []
    for msg in msgs:
        if isinstance(msg, dict):
            serialized.append(msg)
        elif hasattr(msg, "to_dict"):
            serialized.append(msg.to_dict())
        else:
            serialized.append(json.loads(msg.model_dump_json()))
    return serialized
```

### 4. Validation Pattern

**File**: `vllm/entrypoints/openai/protocol.py`

```python
class ResponsesRequest(OpenAIBaseModel):
    background: bool | None = False
    store: bool | None = True

    @model_validator(mode="before")
    def validate_background(cls, data):
        if not data.get("background"):
            return data
        if not data.get("store", True):
            raise ValueError("background can only be used when `store` is true")
        if data.get("stream"):
            raise ValueError("background cannot be used with stream=true")
        return data
```

### 5. Tool Parsing Pattern

**File**: `vllm/entrypoints/openai/serving_responses.py`

```python
def _parse_tool_calls_from_content(
    self,
    content: str,
    request: ResponsesRequest,
    tokenizer: AnyTokenizer
) -> tuple[list[dict], str]:
    if not request.tools:
        return [], content

    # Use model-specific tool parser
    tool_calls = self.tool_parser.extract_tool_calls(
        model_output=content,
        request=request
    )

    # Remove tool calls from content
    remaining_content = self.tool_parser.extract_tool_calls_streaming(
        model_output=content,
        request=request,
        tool_call_only=False
    )

    return tool_calls, remaining_content
```

---

## Response Examples

### 1. Chat Completion Response (JSON)

```json
{
  "id": "chatcmpl-123abc456def",
  "object": "chat.completion",
  "created": 1699564000,
  "model": "meta-llama/Llama-2-7b-chat-hf",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hello! How can I help you today?"
      },
      "finish_reason": "stop",
      "logprobs": null
    }
  ],
  "usage": {
    "prompt_tokens": 15,
    "completion_tokens": 9,
    "total_tokens": 24,
    "prompt_tokens_details": {
      "cached_tokens": 0
    }
  }
}
```

### 2. Chat Completion Stream Chunk (SSE)

```
data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1699564000,"model":"llama-2-7b","choices":[{"index":0,"delta":{"role":"assistant","content":""},"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1699564000,"model":"llama-2-7b","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1699564000,"model":"llama-2-7b","choices":[{"index":0,"delta":{"content":"!"},"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1699564000,"model":"llama-2-7b","choices":[{"index":0,"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":15,"completion_tokens":2,"total_tokens":17}}

data: [DONE]
```

### 3. Responses API Complete Response (JSON)

```json
{
  "id": "resp_abc123def456",
  "created_at": 1699564000,
  "model": "gpt-4",
  "object": "response",
  "status": "completed",
  "output": [
    {
      "type": "message",
      "id": "msg_xyz789",
      "role": "assistant",
      "status": "completed",
      "content": [
        {
          "type": "output_text",
          "text": "The capital of France is Paris.",
          "annotations": []
        }
      ]
    }
  ],
  "parallel_tool_calls": true,
  "temperature": 1.0,
  "tool_choice": "auto",
  "tools": [],
  "top_p": 1.0,
  "background": false,
  "max_output_tokens": 4096,
  "service_tier": "default",
  "truncation": "auto",
  "usage": {
    "input_tokens": 25,
    "output_tokens": 10,
    "total_tokens": 35,
    "input_tokens_details": {
      "cached_tokens": 0,
      "input_tokens_per_turn": [25],
      "cached_tokens_per_turn": [0]
    },
    "output_tokens_details": {
      "reasoning_tokens": 0,
      "tool_output_tokens": 0,
      "output_tokens_per_turn": [10],
      "tool_output_tokens_per_turn": [0]
    }
  }
}
```

### 4. Responses API with Tool Call (JSON)

```json
{
  "id": "resp_tool123",
  "created_at": 1699564000,
  "model": "gpt-4",
  "object": "response",
  "status": "completed",
  "output": [
    {
      "type": "function",
      "id": "call_abc123",
      "call_id": "call_abc123",
      "status": "completed",
      "function": {
        "name": "get_weather",
        "arguments": "{\"location\": \"San Francisco\", \"unit\": \"celsius\"}"
      }
    }
  ],
  "parallel_tool_calls": true,
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "get_weather",
        "description": "Get the current weather in a location",
        "parameters": {
          "type": "object",
          "properties": {
            "location": {"type": "string"},
            "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]}
          },
          "required": ["location"]
        }
      }
    }
  ],
  "usage": {
    "input_tokens": 50,
    "output_tokens": 25,
    "total_tokens": 75,
    "input_tokens_details": {
      "cached_tokens": 0,
      "input_tokens_per_turn": [50],
      "cached_tokens_per_turn": [0]
    },
    "output_tokens_details": {
      "reasoning_tokens": 0,
      "tool_output_tokens": 0,
      "output_tokens_per_turn": [25],
      "tool_output_tokens_per_turn": [0]
    }
  }
}
```

### 5. Responses API Stream Events (SSE)

```
event: response.created
data: {"type":"response.created","sequence_number":0,"response":{"id":"resp_123","status":"in_progress","model":"gpt-4","object":"response","created_at":1699564000}}

event: response.in_progress
data: {"type":"response.in_progress","sequence_number":1,"response_id":"resp_123"}

event: response.output_item.added
data: {"type":"response.output_item.added","sequence_number":2,"output_index":0,"item":{"type":"message","id":"msg_abc123","role":"assistant","status":"in_progress"}}

event: response.content_part.added
data: {"type":"response.content_part.added","sequence_number":3,"content_index":0,"item_id":"msg_abc123","part":{"type":"output_text"}}

event: response.output_text.delta
data: {"type":"response.output_text.delta","sequence_number":4,"delta":"The","item_id":"msg_abc123","content_index":0}

event: response.output_text.delta
data: {"type":"response.output_text.delta","sequence_number":5,"delta":" capital","item_id":"msg_abc123","content_index":0}

event: response.output_text.delta
data: {"type":"response.output_text.delta","sequence_number":6,"delta":" of","item_id":"msg_abc123","content_index":0}

event: response.output_text.delta
data: {"type":"response.output_text.delta","sequence_number":7,"delta":" France","item_id":"msg_abc123","content_index":0}

event: response.output_text.delta
data: {"type":"response.output_text.delta","sequence_number":8,"delta":" is","item_id":"msg_abc123","content_index":0}

event: response.output_text.delta
data: {"type":"response.output_text.delta","sequence_number":9,"delta":" Paris","item_id":"msg_abc123","content_index":0}

event: response.output_text.delta
data: {"type":"response.output_text.delta","sequence_number":10,"delta":".","item_id":"msg_abc123","content_index":0}

event: response.output_text.done
data: {"type":"response.output_text.done","sequence_number":11,"text":"The capital of France is Paris.","item_id":"msg_abc123","content_index":0}

event: response.content_part.done
data: {"type":"response.content_part.done","sequence_number":12,"content_index":0,"item_id":"msg_abc123","part":{"type":"output_text","text":"The capital of France is Paris."}}

event: response.output_item.done
data: {"type":"response.output_item.done","sequence_number":13,"output_index":0,"item":{"type":"message","id":"msg_abc123","role":"assistant","status":"completed","content":[{"type":"output_text","text":"The capital of France is Paris."}]}}

event: response.completed
data: {"type":"response.completed","sequence_number":14,"response":{"id":"resp_123","status":"completed","model":"gpt-4","usage":{"input_tokens":25,"output_tokens":10,"total_tokens":35}}}
```

### 6. Error Response (JSON)

```json
{
  "error": {
    "message": "Invalid request: temperature must be between 0 and 2",
    "type": "invalid_request_error",
    "param": "temperature",
    "code": 400
  }
}
```

---

## Token Usage Tracking

### UsageInfo (Standard)

**File**: `vllm/entrypoints/openai/protocol.py`

```python
class UsageInfo(OpenAIBaseModel):
    prompt_tokens: int = 0
    total_tokens: int = 0
    completion_tokens: int | None = 0
    prompt_tokens_details: PromptTokensDetails | None = None

class PromptTokensDetails(OpenAIBaseModel):
    cached_tokens: int = 0
```

**Example**:
```json
{
  "usage": {
    "prompt_tokens": 100,
    "completion_tokens": 50,
    "total_tokens": 150,
    "prompt_tokens_details": {
      "cached_tokens": 20
    }
  }
}
```

### ResponseUsage (Responses API)

**File**: `vllm/entrypoints/openai/protocol.py`

```python
class InputTokensDetails(OpenAIBaseModel):
    cached_tokens: int
    input_tokens_per_turn: list[int] = Field(default_factory=list)
    cached_tokens_per_turn: list[int] = Field(default_factory=list)

class OutputTokensDetails(OpenAIBaseModel):
    reasoning_tokens: int = 0
    tool_output_tokens: int = 0
    output_tokens_per_turn: list[int] = Field(default_factory=list)
    tool_output_tokens_per_turn: list[int] = Field(default_factory=list)

class ResponseUsage(OpenAIBaseModel):
    input_tokens: int
    input_tokens_details: InputTokensDetails
    output_tokens: int
    output_tokens_details: OutputTokensDetails
    total_tokens: int
```

**Example**:
```json
{
  "usage": {
    "input_tokens": 120,
    "output_tokens": 85,
    "total_tokens": 205,
    "input_tokens_details": {
      "cached_tokens": 30,
      "input_tokens_per_turn": [50, 40, 30],
      "cached_tokens_per_turn": [10, 10, 10]
    },
    "output_tokens_details": {
      "reasoning_tokens": 15,
      "tool_output_tokens": 10,
      "output_tokens_per_turn": [30, 25, 30],
      "tool_output_tokens_per_turn": [5, 0, 5]
    }
  }
}
```

### Building Detailed Usage Info

**File**: `vllm/entrypoints/openai/serving_responses.py`

```python
usage = ResponseUsage(
    input_tokens=num_prompt_tokens,
    output_tokens=num_generated_tokens,
    total_tokens=num_prompt_tokens + num_generated_tokens,
    input_tokens_details=InputTokensDetails(
        cached_tokens=num_cached_tokens,
        input_tokens_per_turn=input_tokens_per_turn,
        cached_tokens_per_turn=cached_tokens_per_turn
    ),
    output_tokens_details=OutputTokensDetails(
        reasoning_tokens=num_reasoning_tokens,
        tool_output_tokens=num_tool_output_tokens,
        output_tokens_per_turn=output_tokens_per_turn,
        tool_output_tokens_per_turn=tool_output_tokens_per_turn
    )
)
```

---

## Additional Resources

### Configuration Files

- **CLI Arguments**: `vllm/entrypoints/openai/cli_args.py`
- **Logging**: `vllm/entrypoints/logger.py`
- **Metrics**: `vllm/entrypoints/openai/orca_metrics.py`

### Utility Files

- **Response Utils**: `vllm/entrypoints/responses_utils.py`
- **Chat Utils**: `vllm/entrypoints/chat_utils.py`
- **Score Utils**: `vllm/entrypoints/score_utils.py`

### Tool Parsers (40+ models)

```
vllm/entrypoints/openai/tool_parsers/
├── granite_tool_parser.py
├── mistral_tool_parser.py
├── llama_tool_parser.py
├── qwen_tool_parser.py
├── hermes_tool_parser.py
└── ... (40+ more)
```

---

## Summary

vLLM provides a comprehensive **OpenAI-compatible REST API** with:

1. **Multiple Response Types**: Chat, Completion, Embedding, Responses API
2. **Streaming Support**: Server-Sent Events (SSE) with named events
3. **Advanced Features**: Tool calling, reasoning, background processing
4. **Robust Error Handling**: Detailed error responses with proper HTTP status codes
5. **Token Tracking**: Detailed per-turn and per-type token usage
6. **OpenAI Compatibility**: Works seamlessly with OpenAI client libraries

The **Responses API** is the most advanced endpoint with:
- Multiple output types (messages, reasoning, tool calls)
- Rich streaming events
- Background processing support
- Tool calling with web search and code interpreter
- Per-turn token tracking

All responses use **Pydantic v2** models for validation and serialization, ensuring type safety and OpenAI API compatibility.
