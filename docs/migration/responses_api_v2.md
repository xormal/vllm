# Migration Guide: OpenAI Responses API → vLLM

This document helps teams migrate existing OpenAI-based workloads (Chat
Completions or earlier vLLM deployments) to the new Responses API interface.

## 1. Audience

- Users currently targeting `/v1/chat/completions` or `/v1/responses` on OpenAI.
- Operators running older vLLM versions without tool outputs, service tiers, or
  compatibility mode.

## 2. Quick Start

1. **Upgrade vLLM** to the commit that includes `responses_stream_buffer_max_bytes`
   and `responses_ping_interval_seconds`.
2. Start the server with compatibility options:

   ```bash
   python -m vllm.entrypoints.openai.api_server \
     --model <MODEL> \
     --responses-compatibility-mode \
     --responses-ping-interval-seconds 15 \
     --responses-default-service-tier auto \
     --responses-allowed-service-tiers auto,default
   ```

3. Update clients to call `/v1/responses` with the same payload they would send
   to OpenAI (ensure `request_id` matches `X-Request-Id` headers).

## 3. Breaking Changes & Resolutions

| Issue | Migration Action |
|-------|------------------|
| **Tool outputs require POST `/responses/{id}/tool_outputs`** | Implement the continuation step (stream `response.tool_call.delta`, execute tool, POST results). |
| **`store=true` required for background** | Set `store` explicitly for background jobs; configure TTL/quotas via `--responses-store-*`. |
| **Per-event SSE validation** | Clients must ignore `response.ping` heartbeats and handle `response.error` when validation fails. |
| **Request ID mismatch errors** | Ensure the `request_id` in JSON matches `X-Request-Id` header. |
| **`service_tier` allowlist** | Choose allowed tiers with `--responses-allowed-service-tiers`; update clients to use supported values only. |

## 4. Feature Parity Checklist

- ✅ `/v1/responses`, `/responses/{id}` (GET/Cancel), `/responses/{id}/tool_outputs`.
- ✅ Streaming events match OpenAI names; set `--responses-compatibility-mode`
  to reject vLLM-only fields.
- ✅ Retry-After headers for 429.
- ✅ Rate limit usage events and headers.
- ✅ Prompt caching via `prompt_cache_key`.
- ✅ Store/backfill responses for reconnection.

## 5. Recommended Server Flags

| Flag | Purpose |
|------|---------|
| `--responses-ping-interval-seconds` | Keeps delegates alive behind proxies. |
| `--max-request-body-bytes` / `--max-stream-event-bytes` | Protects the service from overly large payloads. |
| `--responses-tool-timeout` | Auto-fail tool calls when outputs do not arrive. |
| `--responses-stream-buffer-max-bytes` | Caps SSE memory usage (prevents multi-GB sessions). |
| `--responses-default-service-tier` / `--responses-allowed-service-tiers` | Enforces SLAs per customer tier. |

## 6. Client Changes

- **Streaming**: use `Accept: text/event-stream`. Handle named events instead of
  `delta` streams.
- **Tooling**: parse `response.tool_call.delta`, call tools, POST results.
- **Retries**: respect `Retry-After` header; expect `response.error` SSE events.
- **Heartbeats**: ignore `response.ping`, keep connection open.

## 7. Validation & Testing

- Run unit tests: `python3 -m pytest tests/entrypoints/openai/test_serving_responses.py`.
- For end-to-end verification, replay OpenAI requests against vLLM with
  compatibility mode enabled. Use `curl` to assert SSE events appear in the same
  order (sequence numbers monotonically increase).

## 8. Rollout Strategy

1. Deploy a staging vLLM instance with compatibility mode enabled.
2. Mirror production traffic using read-only tokens to confirm parity.
3. Switch traffic gradually; monitor `response.error` and backlog metrics.
4. Once stable, disable compatibility mode to re-enable advanced vLLM features
   (e.g., `enable_response_messages`, computer call image placeholders).
