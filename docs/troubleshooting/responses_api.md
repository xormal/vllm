# Troubleshooting: Responses API

Common issues when using `/v1/responses` and how to resolve them.

## SSE Stream Closes Prematurely

- Ensure the client sets `Accept: text/event-stream`.
- Check for `response.error` events: they include `error.type/message`.
- Heartbeats (`response.ping`) keep the connection alive; do not treat them as errors.
- If proxies terminate idle connections, lower `--responses-ping-interval-seconds`.

## Tool Output Never Arrives

- The server waits `--responses-tool-timeout` seconds; after that, the stream fails.
- Make sure the tool client POSTs to `/responses/{id}/tool_outputs` with
  the correct `tool_call_id`.
- Duplicate submissions are rejected; log messages clarify the failure.

## `invalid_request_error` on Request IDs

- When sending `X-Request-Id`, the JSON body must contain the same `request_id`.
- Compatibility mode enforces this strictly; disable it for internal clients if necessary.

## Missing `[DONE]` Marker

- Starting with Stage 2, vLLM always emits `data: [DONE]` after `response.completed`.
- If your client doesn’t see it, ensure it reads until EOF; chunked transports may buffer.

## Large Payload Errors

- Check the following CLI caps:
  - `--max-request-body-bytes`
  - `--max-stream-event-bytes`
  - `--responses-stream-buffer-max-bytes`
  - `--max-tool-output-bytes`
- Reduce payload size or raise the limits carefully.

## Stale Sessions / `response not found`

- Streaming sessions expire per `--responses-session-ttl`.
- Call `/responses/{id}` (non-stream) if you need persisted responses (`store=true`).

## Debugging Tips

- Enable debug logging: `export VLLM_LOGGING_LEVEL=DEBUG`.
- Trace SSE output with `curl -N ...` to observe raw `event:` / `data:` frames.
- Run `tests/compliance/test_openai_responses_api.py` against the server to validate endpoints and streaming contract.
