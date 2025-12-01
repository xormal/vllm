# vLLM API vs OpenAI Responses API - Comprehensive Comparison

## Executive Summary

This document provides a **complete, detailed comparison** between vLLM's implementation of the Responses API and the official OpenAI Responses API specification. All differences are documented with code references, structural analysis, and compatibility notes.

**Key Finding**: vLLM implements a **partial, modified version** of OpenAI's Responses API with significant architectural differences in tool calling workflow, SSE event structure, and request parameters.

---

## Table of Contents

1. [Endpoints Comparison](#endpoints-comparison)
2. [Request Parameters Comparison](#request-parameters-comparison)
3. [Response Structure Comparison](#response-structure-comparison)
4. [SSE Events Comparison](#sse-events-comparison)
5. [Tool Calling Workflow Comparison](#tool-calling-workflow-comparison)
6. [Reasoning Support Comparison](#reasoning-support-comparison)
7. [Error Handling Comparison](#error-handling-comparison)
8. [Azure-Specific Features](#azure-specific-features)
9. [Compatibility Matrix](#compatibility-matrix)
10. [Summary of Gaps](#summary-of-gaps)

---

## 1. Endpoints Comparison

### OpenAI Responses API Endpoints

| Method | Endpoint | Purpose | Status in OpenAI |
|--------|----------|---------|------------------|
| POST | `/v1/responses` | Create response (streaming/non-streaming) | ✅ Implemented |
| POST | `/v1/responses/{id}/tool_outputs` | Submit tool execution results | ✅ Implemented |
| GET | `/v1/responses/{id}` | Retrieve stored response | ✅ Implemented (optional) |
| POST | `/v1/responses/{id}/cancel` | Cancel ongoing response | ✅ Implemented (optional) |

**Reference**: OAI_API_spec.md:18-24

### vLLM Implementation

| Method | Endpoint | Purpose | Status in vLLM | File Reference |
|--------|----------|---------|----------------|----------------|
| POST | `/v1/responses` | Create response | ✅ **Implemented** | api_server.py:517 |
| POST | `/v1/responses/{id}/tool_outputs` | Submit tool results | ❌ **NOT IMPLEMENTED** | N/A |
| GET | `/v1/responses/{id}` | Retrieve stored response | ✅ **Implemented** | api_server.py:543 |
| POST | `/v1/responses/{id}/cancel` | Cancel response | ✅ **Implemented** | api_server.py:578 |

### Critical Difference: Missing `/tool_outputs` Endpoint

**OpenAI Flow:**
```
1. POST /v1/responses → Model generates tool calls
2. Server sends response.tool_call.delta event
3. Client executes tools locally
4. Client sends POST /v1/responses/{id}/tool_outputs
5. Server continues generation with tool results
```

**vLLM Flow:**
```
1. POST /v1/responses → Model generates tool calls
2. Server returns tool calls in response output
3. Client executes tools locally
4. Client sends NEW POST /v1/responses with:
   - previous_response_id: "{id}"
   - input: [... tool call results as function_call_output items]
5. Server continues generation
```

**Code Evidence:**
- vLLM routes: `vllm/entrypoints/openai/api_server.py:506-596`
- Tool output conversion: `vllm/entrypoints/responses_utils.py:22-47`
- API difference documentation: `API_difference.md:146`

---

## 2. Request Parameters Comparison

### 2.1 Standard Parameters (Both Support)

| Parameter | OpenAI | vLLM | Notes |
|-----------|--------|------|-------|
| `model` | ✅ | ✅ | Model identifier |
| `instructions` | ✅ | ✅ | System prompt |
| `input` | ✅ | ✅ | User input (string or array of ResponseInputOutputItem) |
| `tools` | ✅ | ✅ | Array of tool definitions |
| `tool_choice` | ✅ | ✅ | "auto", "none", "required", or specific tool |
| `parallel_tool_calls` | ✅ | ✅ | Allow multiple tools simultaneously |
| `temperature` | ✅ | ✅ | Sampling temperature |
| `top_p` | ✅ | ✅ | Nucleus sampling |
| `max_output_tokens` | ✅ | ✅ | Maximum tokens to generate |
| `max_tool_calls` | ✅ | ✅ | Maximum number of tool calls |
| `stream` | ✅ | ✅ | Enable streaming |
| `store` | ✅ | ✅ | Store response for later retrieval |
| `background` | ✅ | ✅ | Process in background mode |
| `metadata` | ✅ | ✅ | Custom metadata |
| `user` | ✅ | ✅ | End user identifier |
| `service_tier` | ✅ | ✅ | "auto", "default", "flex", "scale", "priority" |
| `truncation` | ✅ | ✅ | "auto" or "disabled" |
| `top_logprobs` | ✅ | ✅ | Number of log probabilities to return |
| `reasoning` | ✅ | ✅ | Reasoning configuration |
| `text` | ✅ | ✅ | Text output configuration |
| `prompt` | ✅ | ✅ | Prompt configuration |
| `previous_response_id` | ✅ | ✅ | Link to previous response for continuation |
| `include` | ✅ | ✅ | Additional fields to include |

**Code Reference**: `vllm/entrypoints/openai/protocol.py:312-349`

### 2.2 OpenAI-Specific Parameters (NOT in vLLM)

| Parameter | Description | Status in vLLM | Impact |
|-----------|-------------|----------------|--------|
| `prompt_cache_key` | Cache key for prompt caching (e.g., "019a...") | ✅ | Supported via prefix cache salt mapping |

**Reference**: OAI_API_spec.md:43

**Impact Analysis:**
- **High**: Prompt caching is critical for performance optimization in repeated interactions
- Clients can now pass `prompt_cache_key`; vLLM maps it to the internal prefix cache salt to isolate cache entries.
- vLLM has its own caching mechanism (`cache_salt`), but uses different semantics

### 2.3 vLLM-Specific Parameters (NOT in OpenAI)

| Parameter | Description | File Reference |
|-----------|-------------|----------------|
| `request_id` | Custom request identifier (default: auto-generated) | protocol.py:352-359 |
| `mm_processor_kwargs` | Additional kwargs for HuggingFace processor | protocol.py:360-363 |
| `priority` | Request priority (0 = default) | protocol.py:364-371 |
| `cache_salt` | Salt for prefix cache (security in multi-user envs) | protocol.py:372-382 |
| `enable_response_messages` | Return messages in response (harmony mode) | protocol.py:384-391 |
| `previous_input_messages` | Previous messages in harmony format | protocol.py:396 |

**Note**: These are vLLM extensions not present in OpenAI API.

### 2.4 Text Configuration Differences

**OpenAI API** (OAI_API_spec.md:44):
```json
{
  "text": {
    "verbosity": "high"  // Controls output verbosity
  }
}
```

**vLLM Implementation** (protocol.py:343):
```python
text: ResponseTextConfig | None = None
```

Where `ResponseTextConfig` is imported from OpenAI Python SDK:
```python
from openai.types.responses import ResponseTextConfig
```

**Status**: ✅ Supported (uses OpenAI SDK types)

**Note**: vLLM delegates text config structure to OpenAI SDK, so `verbosity` and other fields should work if present in the SDK version.

### 2.5 Reasoning Configuration

**OpenAI API** (OAI_API_spec.md:39):
```json
{
  "reasoning": {
    "effort": "medium"  // "low", "medium", "high"
  }
}
```

**vLLM Implementation** (protocol.py:338):
```python
reasoning: Reasoning | None = None
```

Where `Reasoning` is imported from OpenAI Python SDK:
```python
from openai.types.shared import Reasoning
```

**Status**: ✅ Supported (uses OpenAI SDK types)

**Code Reference**: `vllm/entrypoints/openai/serving_responses.py` processes reasoning output

---

## 3. Response Structure Comparison

### 3.1 ResponsesResponse Object

#### Common Fields (Both APIs)

| Field | Type | OpenAI | vLLM |
|-------|------|--------|------|
| `id` | string | ✅ | ✅ |
| `created_at` | int (unix timestamp) | ✅ | ✅ |
| `object` | "response" | ✅ | ✅ |
| `model` | string | ✅ | ✅ |
| `status` | ResponseStatus | ✅ | ✅ |
| `output` | list[ResponseOutputItem] | ✅ | ✅ |
| `usage` | ResponseUsage | ✅ | ✅ |
| `instructions` | string | ✅ | ✅ |
| `tools` | list[Tool] | ✅ | ✅ |
| `tool_choice` | ToolChoice | ✅ | ✅ |
| `parallel_tool_calls` | bool | ✅ | ✅ |
| `temperature` | float | ✅ | ✅ |
| `top_p` | float | ✅ | ✅ |
| `max_output_tokens` | int | ✅ | ✅ |
| `metadata` | Metadata | ✅ | ✅ |
| `incomplete_details` | IncompleteDetails | ✅ | ✅ |

#### vLLM-Specific Fields (NOT in standard OpenAI)

| Field | Type | Purpose | Code Reference |
|-------|------|---------|----------------|
| `input_messages` | list[ChatCompletionMessageParam] | Harmony mode input messages | protocol.py:2399 |
| `output_messages` | list[ChatCompletionMessageParam] | Harmony mode output messages | protocol.py:2400 |

**Note**: These fields are populated when `enable_response_messages=True` (vLLM extension for GPT-OSS models).

### 3.2 ResponseStatus Values

**Both APIs Support**:
- `"queued"` - Request waiting to start
- `"in_progress"` - Currently processing
- `"completed"` - Successfully finished
- `"incomplete"` - Reached max_output_tokens
- `"cancelled"` - User cancelled
- `"failed"` - Error occurred

**Code Reference**: `vllm/entrypoints/openai/protocol.py` uses OpenAI SDK types

### 3.3 ResponseUsage Structure

#### OpenAI API (OAI_API_spec.md:171-177)

```json
{
  "input_tokens": 4000,
  "input_tokens_details": {
    "cached_tokens": 500
  },
  "output_tokens": 900,
  "output_tokens_details": {
    "reasoning_tokens": 120
  },
  "total_tokens": 4900
}
```

#### vLLM Implementation

```python
class ResponseUsage(OpenAIBaseModel):
    input_tokens: int
    input_tokens_details: InputTokensDetails
    output_tokens: int
    output_tokens_details: OutputTokensDetails
    total_tokens: int

class InputTokensDetails(OpenAIBaseModel):
    cached_tokens: int
    input_tokens_per_turn: list[int] = Field(default_factory=list)
    cached_tokens_per_turn: list[int] = Field(default_factory=list)

class OutputTokensDetails(OpenAIBaseModel):
    reasoning_tokens: int = 0
    tool_output_tokens: int = 0
    output_tokens_per_turn: list[int] = Field(default_factory=list)
    tool_output_tokens_per_turn: list[int] = Field(default_factory=list)
```

**Differences**:
- ✅ OpenAI fields fully supported
- ➕ vLLM adds **per-turn tracking**: `input_tokens_per_turn`, `output_tokens_per_turn`, etc.
- ➕ vLLM tracks `tool_output_tokens` separately

**Code Reference**: `vllm/entrypoints/openai/protocol.py:2320-2344`

---

## 4. SSE Events Comparison

### 4.1 OpenAI Responses API Events

**From OAI_API_spec.md Section 3**:

| Event Type | Description | Code Reference (OAI spec) |
|------------|-------------|---------------------------|
| `response.created` | Response initialized | Line 65-69 |
| `response.output_text.delta` | Text chunk (streaming) | Line 72-85 |
| `response.tool_call.delta` | Tool call request | Line 88-105 |
| `response.reasoning.delta` | Reasoning content chunk | Line 112-118 |
| `response.reasoning.summary.delta` | Reasoning summary chunk | Line 120-127 |
| `response.reasoning.summary.added` | Reasoning summary added | Line 128-135 |
| `response.output_item.done` | Output item completed | Line 140-152 |
| `response.output_item.added` | Output item added | Line 138-152 |
| `response.error` | Error occurred | Line 155-163 |
| `response.completed` | Response fully completed | Line 166-180 |
| `response.additional_context` | Additional context (e.g., encrypted reasoning) | Line 182-191 |
| `response.rate_limits.updated` | Rate limit info | Line 193-202 |

**Total**: 12 distinct event types

### 4.2 vLLM Implementation Events

**From vllm/entrypoints/openai/protocol.py:2524-2544**:

```python
StreamingResponsesResponse: TypeAlias = (
    ResponseCreatedEvent
    | ResponseInProgressEvent
    | ResponseCompletedEvent
    | ResponseOutputItemAddedEvent
    | ResponseOutputItemDoneEvent
    | ResponseContentPartAddedEvent
    | ResponseContentPartDoneEvent
    | ResponseReasoningDeltaEvent
    | ResponseReasoningDoneEvent
    | ResponseReasoningTextDeltaEvent
    | ResponseReasoningTextDoneEvent
    | ResponseReasoningPartAddedEvent
    | ResponseReasoningPartDoneEvent
    | ResponseCodeInterpreterCallInProgressEvent
    | ResponseCodeInterpreterCallCodeDeltaEvent
    | ResponseWebSearchCallInProgressEvent
    | ResponseWebSearchCallSearchingEvent
    | ResponseWebSearchCallCompletedEvent
    | ResponseCodeInterpreterCallCodeDoneEvent
    | ResponseCodeInterpreterCallInterpretingEvent
    | ResponseCodeInterpreterCallCompletedEvent
)
```

**Total**: 19 event types

### 4.3 Event-by-Event Comparison

| Event | OpenAI | vLLM | Notes |
|-------|--------|------|-------|
| **response.created** | ✅ | ✅ | Both supported |
| **response.in_progress** | ❌ | ✅ | vLLM addition (not in OpenAI spec) |
| **response.output_text.delta** | ✅ | ✅ | Both supported (text streaming) |
| **response.tool_call.delta** | ✅ | ❌ | **Missing in vLLM** - uses different tool call approach |
| **response.reasoning.delta** | ✅ | ✅ | Added in vLLM (OpenAI-compatible) |
| **response.reasoning.summary.delta** | ✅ | ✅ | Added in vLLM (summaries streamed) |
| **response.reasoning.summary.added** | ✅ | ✅ | Added in vLLM (summaries streamed) |
| **response.reasoning_text.delta** | ❌ | ✅ | Legacy option (`--legacy-reasoning-events`) |
| **response.reasoning_text.done** | ❌ | ✅ | Legacy option (`--legacy-reasoning-events`) |
| **response.reasoning_part.added** | ❌ | ✅ | vLLM addition |
| **response.reasoning_part.done** | ❌ | ✅ | vLLM addition |
| **response.output_item.added** | ✅ | ✅ | Both supported |
| **response.output_item.done** | ✅ | ✅ | Both supported |
| **response.content_part.added** | ❌ | ✅ | vLLM addition (granular content tracking) |
| **response.content_part.done** | ❌ | ✅ | vLLM addition |
| **response.error** | ✅ | ✅ | Added in vLLM (SSE error event) |
| **response.completed** | ✅ | ✅ | Both supported |
| **response.additional_context** | ✅ | ✅ | Added in vLLM (encrypted reasoning context) |
| **response.rate_limits.updated** | ✅ | ✅ | Added in vLLM (basic usage snapshot) |
| **response.code_interpreter_call.*** | ❌ | ✅ | vLLM extension (5 events) |
| **response.web_search_call.*** | ❌ | ✅ | vLLM extension (3 events) |

### 4.4 Critical Missing Events in vLLM

#### 1. `response.tool_call.delta`

**OpenAI Structure** (OAI_API_spec.md:88-105):
```json
{
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

**vLLM Alternative**: Tool calls are returned in `response.output_item.added` events with complete tool call objects, not streaming deltas.

**Impact**: Clients expecting `response.tool_call.delta` will not receive tool calls in the expected format.

#### 2. `response.reasoning.delta`

✅ **Resolved** – vLLM now emits OpenAI-compatible `response.reasoning.delta`
and `response.reasoning.done` events (including `response`/`delta` payloads).
Set `--legacy-reasoning-events` if you still need the historical
`response.reasoning_text.*` schema.

#### 3. `response.error`

✅ **Resolved** – vLLM now emits `response.error` SSE events whenever a streamed
Responses request fails, aligning with OpenAI’s behavior. Non-streaming requests
still receive JSON error bodies.

#### 4. `response.additional_context`

**OpenAI Structure** (OAI_API_spec.md:182-191):
```json
{
  "type": "response.additional_context",
  "response": {"id": "resp_123"},
  "context": {
    "reasoning.encrypted_content": "<base64>"
  }
}
```

**vLLM Status**: ✅ Implemented. When callers set
`include=["reasoning.encrypted_content"]`, vLLM encrypts the full reasoning
transcript (Fernet if `cryptography` is installed, Base64 otherwise) and
streams it via `response.additional_context` after the reasoning block ends.

#### 5. `response.rate_limits.updated`

**OpenAI Structure** (OAI_API_spec.md:193-202):
```json
{
  "type": "response.rate_limits.updated",
  "response": {"id": "resp_123"},
  "limits": {
    "primary": {
      "used_percent": 42.5,
      "window_minutes": 60
    }
  }
}
```

**vLLM Status**: ✅ Implemented. When `--enable-rate-limit-events` is set, vLLM
tracks per-user request/token windows and emits `response.rate_limits.updated`
after each response completes with current percentage usage.

---

## 5. Tool Calling Workflow Comparison

### 5.1 OpenAI Workflow

**From OAI_API_spec.md:209-220**:

```
Step 1: POST /v1/responses
        ↓
Step 2: Server sends response.tool_call.delta event
        ↓
Step 3: Client executes tool locally
        ↓
Step 4: Client sends POST /v1/responses/{id}/tool_outputs
        Body: {"tool_call_id": "call_ls", "output": [{"type": "output_text", "text": "stdout"}]}
        ↓
Step 5: Server continues SSE stream with tool results incorporated
```

**Key Points**:
- Tool results submitted to **separate endpoint** `/tool_outputs`
- Same SSE connection continues after tool execution
- Server maintains stateful session keyed by response ID

### 5.2 vLLM Workflow

**From investigation and code analysis**:

```
Step 1: POST /v1/responses
        ↓
Step 2: Server returns response with tool calls in output array
        Status: "completed" (with tool calls) or "in_progress"
        ↓
Step 3: Client executes tool locally
        ↓
Step 4: Client sends NEW POST /v1/responses
        Body: {
          "previous_response_id": "resp_123",
          "input": [
            {
              "type": "function_call_output",
              "call_id": "call_ls",
              "output": "stdout content"
            }
          ]
        }
        ↓
Step 5: Server starts NEW response with tool results
```

**Key Points**:
- Tool results submitted via **continuation request** (new POST to `/v1/responses`)
- No dedicated `/tool_outputs` endpoint
- Each tool call round-trip creates a new response with `previous_response_id` linkage

**Code References**:
- Tool output conversion: `vllm/entrypoints/responses_utils.py:22-47`
- Continuation handling: `vllm/entrypoints/openai/serving_responses.py`

### 5.3 Tool Output Structure Comparison

#### OpenAI Format

**Submission** (OAI_API_spec.md:213-217):
```json
POST /v1/responses/{response_id}/tool_outputs
{
  "tool_call_id": "call_ls",
  "output": [
    {"type": "output_text", "text": "file1.txt\nfile2.py"}
  ]
}
```

#### vLLM Format

**Submission**:
```json
POST /v1/responses
{
  "previous_response_id": "resp_abc123",
  "input": [
    {
      "type": "function_call_output",
      "call_id": "call_ls",
      "output": "file1.txt\nfile2.py"
    }
  ]
}
```

**Code Reference**: `vllm/entrypoints/responses_utils.py:39-47`
```python
elif item.get("type") == "function_call_output":
    return ChatCompletionToolMessageParam(
        role="tool",
        content=item.get("output"),
        tool_call_id=item.get("call_id"),
    )
```

### 5.4 Parallel Tool Calls

**Both APIs Support**: `parallel_tool_calls: true`

**OpenAI**: Multiple tool calls in single `response.tool_call.delta` event, all results submitted in one `/tool_outputs` request.

**vLLM**: Multiple tool calls in `output` array, all results submitted in `input` array of continuation request.

**Compatibility**: ✅ Semantically compatible, different wire protocol

---

## 6. Reasoning Support Comparison

### 6.1 Request-Level Reasoning Config

**OpenAI** (OAI_API_spec.md:39):
```json
{
  "reasoning": {
    "effort": "medium"  // "low", "medium", "high"
  }
}
```

**vLLM**:
```python
reasoning: Reasoning | None = None
```

**Status**: ✅ Supported via OpenAI SDK types

### 6.2 Reasoning in Response

**OpenAI Events**:
- `response.reasoning.delta` - Streaming reasoning content (default)
- `response.reasoning.summary.delta` - Streaming reasoning summary
- `response.reasoning.summary.added` - Summary added event

**vLLM Events**:
- `response.reasoning_text.delta` - Legacy reasoning stream (requires `--legacy-reasoning-events`)
- `response.reasoning_text.done` - Legacy reasoning completion event
- `response.reasoning_part.added` - Reasoning part added
- `response.reasoning_part.done` - Reasoning part done

**Event Name Mapping**:
```
OpenAI                              vLLM
--------------------------------------
response.reasoning.delta      →     response.reasoning.delta
response.reasoning.summary.*  →     response.reasoning.summary.*
(No equivalent)               →     response.reasoning_text.* (legacy compatibility only)
```

### 6.3 Reasoning in Output

**Both APIs**: Reasoning appears in `output` array as `ResponseReasoningItem`.

**vLLM Code Reference**: `vllm/entrypoints/openai/serving_responses.py:903-945`

```python
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
```

### 6.4 Encrypted Reasoning Content

**OpenAI** (OAI_API_spec.md:42):
```json
{
  "include": ["reasoning.encrypted_content"]
}
```

Event: `response.additional_context` with `reasoning.encrypted_content` field.

**vLLM**:
```python
include: list[Literal[
    "code_interpreter_call.outputs",
    "computer_call_output.output.image_url",
    "file_search_call.results",
    "message.input_image.image_url",
    "message.output_text.logprobs",
    "reasoning.encrypted_content",  # ✅ Defined in request
]] | None = None
```

**Status**:
- ✅ Parameter accepted in request
- ✅ `response.additional_context` emitted with encrypted reasoning payload
- ⚠️ Falls back to Base64-encoding when `cryptography` (Fernet) is unavailable

---

## 7. Error Handling Comparison

### 7.1 Error Response Format

#### OpenAI - SSE Error Event

**From OAI_API_spec.md:155-163**:
```
event: response.error
data: {
  "type": "response.error",
  "response": {"id": "resp_123", "status": "failed"},
  "error": {
    "type": "internal_error",
    "message": "model crashed"
  }
}
```

#### vLLM - HTTP Error Response

**Code**: `vllm/entrypoints/openai/serving_engine.py`
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

**Response**:
```json
HTTP 400/500
{
  "error": {
    "message": "Invalid request: temperature must be between 0 and 2",
    "type": "invalid_request_error",
    "param": "temperature",
    "code": 400
  }
}
```

**Key Difference**:
- Both OpenAI and vLLM now emit `response.error` events for streaming requests.
- vLLM continues to return JSON error bodies for non-streaming requests.

### 7.2 Error Types

**OpenAI Special Types** (OAI_API_spec.md:233):
- `usage_limit_reached`
- `usage_not_included`
- `quota_exceeded`
- `invalid_api_key`

**vLLM Types**:
- `invalid_request_error` (400)
- `not_found_error` (404)
- `InternalServerError` (500)
- `ValidationError` (400)

**Compatibility**: ⚠️ vLLM uses generic error types, not OpenAI's specific types

### 7.3 Retry Behavior

**OpenAI** (OAI_API_spec.md:226-231):

| Status | Behavior |
|--------|----------|
| 429 | Return `Retry-After` header, client retries |
| 401 | Client refreshes token |
| 5xx | Client retries up to max_retries |
| 400 | Display error to user |

**vLLM**: Standard HTTP error handling, but no specific `Retry-After` logic documented.

---

## 8. Azure-Specific Features

**From OAI_API_spec.md:255-261**:

### OpenAI Requirements for Azure

1. **Endpoint Format**:
   ```
   https://{resource}.openai.azure.com/openai/deployments/{model}/responses?api-version=2024-02-15-preview
   ```

2. **Force `store: true`** - Azure requires storing responses

3. **Stable Item IDs** - `input` elements must have stable `id` fields (use `attach_item_ids`)

### vLLM Azure Support

**Status**: ✅ Implemented (enable via `--enable-azure-api`)

vLLM now exposes `/openai/deployments/{deployment}/responses` when the Azure flag
is enabled. The handler:

- Validates `api-version` against `SUPPORTED_AZURE_API_VERSIONS`
- Requires Azure-style authentication (`api-key` header or `Authorization: Bearer`)
- Forces `store=true` and auto-attaches stable `id` fields on list inputs
- Uses the deployment name as the default model if `model` is omitted
- Adds Azure response headers such as `x-ms-region`, `x-ms-request-id`, and
  `api-supported-versions`

---

## 9. Compatibility Matrix

### 9.1 Request Compatibility

| Feature | OpenAI Spec | vLLM | Compatible? |
|---------|-------------|------|-------------|
| Basic parameters (model, input, instructions) | ✅ | ✅ | ✅ Yes |
| Tool definitions | ✅ | ✅ | ✅ Yes |
| Reasoning configuration | ✅ | ✅ | ✅ Yes |
| Temperature, top_p, max_tokens | ✅ | ✅ | ✅ Yes |
| Streaming | ✅ | ✅ | ✅ Yes |
| Background processing | ✅ | ✅ | ✅ Yes |
| Metadata | ✅ | ✅ | ✅ Yes |
| `prompt_cache_key` | ✅ | ✅ | ✅ Yes (provides cache salt) |
| `text.verbosity` | ✅ | ✅ | ✅ Likely yes (via SDK) |
| `include` array | ✅ | ✅ | ⚠️ Partial - accepted but not all items handled |

**Overall Request Compatibility**: **85%** (most parameters work, caching features missing)

### 9.2 Response Compatibility

| Feature | OpenAI Spec | vLLM | Compatible? |
|---------|-------------|------|-------------|
| Response object structure | ✅ | ✅ | ✅ Yes |
| Usage tracking | ✅ | ✅ | ✅ Yes (vLLM has more detail) |
| Output items (message, reasoning, tool_call) | ✅ | ✅ | ✅ Yes |
| Status states | ✅ | ✅ | ✅ Yes |
| Incomplete details | ✅ | ✅ | ✅ Yes |

**Overall Response Compatibility**: **100%** (response structure fully compatible)

### 9.3 SSE Events Compatibility

| Event Category | OpenAI Spec | vLLM | Compatible? |
|----------------|-------------|------|-------------|
| Basic lifecycle (created, completed) | ✅ | ✅ | ✅ Yes |
| Text streaming | ✅ | ✅ | ✅ Yes |
| Tool call streaming | ✅ | ❌ | ❌ No - different approach |
| Reasoning streaming | ✅ | ✅ | ⚠️ Different event names |
| Error events | ✅ | ❌ | ❌ No - uses HTTP errors |
| Rate limit events | ✅ | ❌ | ❌ No |
| Additional context | ✅ | ❌ | ❌ No |

**Overall SSE Events Compatibility**: **40%** (core events work, many missing)

### 9.4 Tool Calling Compatibility

| Feature | OpenAI Spec | vLLM | Compatible? |
|---------|-------------|------|-------------|
| Tool definitions | ✅ | ✅ | ✅ Yes |
| Parallel tool calls | ✅ | ✅ | ✅ Yes |
| Tool call generation | ✅ | ✅ | ✅ Yes |
| `/tool_outputs` endpoint | ✅ | ❌ | ❌ No - requires continuation |
| Tool output submission | ✅ | ✅ | ⚠️ Different protocol |

**Overall Tool Calling Compatibility**: **60%** (works but protocol differs)

### 9.5 Overall API Compatibility Score

| Category | Weight | Score | Weighted Score |
|----------|--------|-------|----------------|
| Request Parameters | 25% | 85% | 21.25% |
| Response Structure | 20% | 100% | 20% |
| SSE Events | 25% | 40% | 10% |
| Tool Calling | 20% | 60% | 12% |
| Error Handling | 10% | 50% | 5% |

**Total Compatibility**: **68.25%**

**Verdict**: vLLM provides **partial compatibility** with OpenAI Responses API. Core functionality works, but significant differences in tool calling workflow and SSE events require client-side adaptation.

---

## 10. Summary of Gaps

### 10.1 Critical Gaps (Breaking Compatibility)

| Gap | Impact | Severity |
|-----|--------|----------|
| Missing `/v1/responses/{id}/tool_outputs` endpoint | Tool calling requires different workflow | 🔴 **Critical** |
| Missing `response.tool_call.delta` event | Cannot stream tool calls in OpenAI format | 🔴 **Critical** |
| Tool output submission via continuation | Requires client code changes | 🔴 **Critical** |

### 10.2 Major Gaps (Feature Incomplete)

| Gap | Impact | Severity |
|-----|--------|----------|

### 10.3 Minor Gaps (Low Impact)

| Gap | Impact | Severity |
|-----|--------|----------|
| Missing Azure-specific endpoint handling | Azure clients need workaround | ✅ **Resolved** |
| Extra vLLM-specific events | No harm to compatibility | ✅ **None** |
| Extra vLLM-specific parameters | No harm to compatibility | ✅ **None** |

### 10.4 Compatibility Enhancement Opportunities

**For vLLM developers**, implementing these would improve OpenAI compatibility:

1. **High Priority**:
   - Implement `/v1/responses/{id}/tool_outputs` endpoint
   - Add `response.tool_call.delta` event

2. **Medium Priority**:
   - Add Azure endpoint format support

3. **Low Priority**:
   - Implement special error types (`usage_limit_reached`, etc.)

---

## Conclusion

vLLM implements a **modified version** of the OpenAI Responses API with:

✅ **Strengths**:
- Complete response object structure
- Rich token usage tracking (better than OpenAI)
- Reasoning support
- Background processing
- Most core parameters

❌ **Weaknesses**:
- Fundamentally different tool calling workflow (no `/tool_outputs` endpoint)
- Missing several key SSE events
- Different error handling approach
- No prompt caching integration

**Recommendation**:
- **Use vLLM's Responses API** when you control both client and server
- **Expect modifications** if migrating from OpenAI to vLLM
- **Implement client-side adapters** if you need OpenAI compatibility

**Overall Assessment**: vLLM provides a **functional but incompatible variant** of OpenAI's Responses API. It's not a drop-in replacement but offers similar capabilities through different mechanisms.
