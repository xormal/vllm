# OpenAI Responses API Compatibility Guide

This guide documents the differences (and similarities) between vLLM's
Responses API implementation and OpenAI's official service.

## Overview

- **Endpoints**: `/v1/responses`, `/v1/responses/{id}`, `/v1/responses/{id}/cancel`,
  `/v1/responses/{id}/tool_outputs`.
- **Protocol**: FastAPI-based, HTTP/1.1 keep-alive, SSE streaming (`Accept: text/event-stream`).
- **Auth & Headers**: Supports `Authorization: Bearer <token>`,
  `OpenAI-Organization`, `OpenAI-Version`, and echoes `X-Request-Id`.
- **Compatibility Mode**: `--responses-compatibility-mode` rejects vLLM-only fields,
  restricts `include` to official targets, and enforces `request_id` consistency.

## Feature Matrix

| Capability | OpenAI | vLLM | Notes |
|------------|--------|------|-------|
| `/responses` endpoint | ✅ | ✅ | JSON & SSE. |
| `/responses/{id}/tool_outputs` | ✅ | ✅ | Identical schema; duplicates rejected. |
| Streaming events | ✅ | ✅ | `response.*` + vLLM `response.ping`. |
| `[DONE]` terminator | ✅ | ✅ | Always emitted in vLLM SSE. |
| Reasoning events | ✅ | ✅ | `response.reasoning.*`, `response.reasoning.summary.*`, `response.additional_context`. |
| Tool call streaming | ✅ | ✅ | `response.tool_call.delta`. |
| Background responses | ✅ | ✅ | Requires `store=true`. |
| Prompt cache key | ✅ | ✅ | Maps to `cache_salt`. |
| Service tiers | ✅ (`auto`, etc.) | ✅ | Controlled via CLI flags. |
| Rate limits | ✅ | ✅ | Headers + `response.rate_limits.updated`. |
| Retry-After header | ✅ | ✅ | SSE + JSON errors include it. |
| Heartbeat events | ❌ | 🟢 (`response.ping`) | Set `--responses-ping-interval-seconds` to tune/disable. |
| Backward-compat fields (`enable_response_messages`, etc.) | ❌ | 🟡 | Use compatibility mode to disable. |

## Known Behavioral Notes

1. **Heartbeats**: vLLM emits `response.ping` to keep connections alive. Clients
   can safely ignore these events.
2. **Event Validation**: The server validates event types/sequence numbers before
   sending. Malformed events trigger a `response.error`.
3. **Large Payloads**: `--max-request-body-bytes`, `--max-stream-event-bytes`,
   `--responses-stream-buffer-max-bytes` guard against oversize requests/results.
4. **Request IDs**: If the client sends `X-Request-Id`, the same value must appear
   in the JSON `request_id`; otherwise the request is rejected.

## Recommended Server Flags for Full Compatibility

```bash
python -m vllm.entrypoints.openai.api_server \
  --model <MODEL> \
  --responses-compatibility-mode \
  --responses-ping-interval-seconds 15 \
  --responses-default-service-tier auto \
  --responses-allowed-service-tiers auto,default \
  --max-request-body-bytes 1048576 \
  --max-stream-event-bytes 524288 \
  --responses-stream-buffer-max-bytes 16777216 \
  --responses-tool-timeout 300
```

## Client Migration Checklist

- ✅ Switch to `/v1/responses` (OpenAI SDKs support it via `client.responses.*`).
- ✅ Handle streaming events by name (not `choices[].delta`).
- ✅ Implement the tool-output callback if you rely on tool calling.
- ✅ Respect `Retry-After` headers when receiving `429`.
- ✅ Ignore `response.ping` heartbeats.

## Validation Resources

- `tests/compliance/test_openai_responses_api.py` – run against your deployment.
- `docs/serving/responses_api.md` – API reference.
- `docs/migration/responses_api_v2.md` – rolling upgrade guidance.
