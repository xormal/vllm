# Tool Call Streaming: Debug Logging Guide

This document explains how to inspect the end‑to‑end lifecycle of tool calls
in the Responses API stream using server‑side DEBUG logs. It helps validate
that the server emits the canonical sequence of SSE events and quickly locates
breaks in the chain that can stall a turn.

## When To Use

Use this guide when a client reports that tool calls appear to “hang” or a UI
shows a long‑running “Working…” state. Typical symptoms:

- Client executed the tool locally and shows a result, but the model does not
  continue the turn.
- The client logs contain tool results, while the server stream seems to end
  prematurely (e.g., jumps to `response.completed` without a finisher).

## Enabling DEBUG Logs

The tool‑call breadcrumbs are logged at DEBUG level under the standard vLLM
logger for `vllm.entrypoints.openai.serving_responses`. Run your server with
DEBUG logging enabled in your environment (examples):

- Set your process logging level to DEBUG (e.g., via your process manager or
  wrapper). Many setups accept an env var like `LOGLEVEL=DEBUG` or framework
  flags (uvicorn/gunicorn). If unsure, run in an environment where Python’s
  root level is DEBUG.
- Then grep for `TOOL_CALL` lines in server logs:

```bash
journalctl -u vllm | rg "TOOL_CALL"   # or
python -m vllm.entrypoints.openai.api_server ... 2>&1 | rg TOOL_CALL
```

## What Gets Logged

The server logs the 4 key phases of a tool call. Each line contains
`response_id` and stable identifiers you can correlate with SSE events:

- TOOL_CALL added
  - Emitted with `response.output_item.added` when a tool call is created.
  - Fields: `response`, `item_id`, `call_id`, `name`.

- TOOL_CALL delta
  - Emitted with each `response.tool_call.delta` (delta is a string payload).
  - Fields: `response`, `call_id`, `name`, `args_len` (current length of
    accumulated arguments text).

- TOOL_CALL completed
  - Emitted with `response.tool_call.completed` when argument streaming for
    this `call_id` is closed and the client may proceed to run the tool.
  - Fields: `response`, `call_id`.
  - Variants:
    - `(compat)`: issued when running in compatibility mode for clients that do
      not POST `/tool_outputs` — the server completes and closes pending calls
      without waiting.

- TOOL_CALL done
  - Emitted with `response.output_item.done` (function_call variant), signaling
    that the tool call item is finished and the model may continue generation.
  - Fields: `response`, `call_id`, `name`, `args_len`.
  - Variants: `(compat)` like above when the server finalizes pending calls.

Additionally, when a new `POST /v1/responses` continues a previous response
(`previous_response_id`) and the prior turn left a tool call `in_progress`, the
server emits:

- TOOL_CALL finalize prev
  - Emits `response.tool_call.completed` for the old `call_id`.
- TOOL_CALL done prev
  - Emits `response.output_item.done` (function_call) for that `call_id`.

These are sent before new generation begins, closing the loop for clients that
execute tools locally between turns.

## Mapping To SSE Events

Each breadcrumb maps to standard Responses API SSE events:

- added → `response.output_item.added` (function_call, `status=in_progress`)
- delta → `response.tool_call.delta` (string payload)
- completed → `response.tool_call.completed`
- done → `response.output_item.done` (function_call, `status=completed`)

Terminal ordering within a turn:

```
…
response.tool_call.delta → response.tool_call.completed → response.output_item.done → response.completed
```

## Sample Investigation Flow

1) Trigger a tool call and capture logs:

```bash
rg "(TOOL_CALL|response\.tool_call|response\.output_item)" server.log
```

2) Verify you see the 4 phases in order for the same `call_id`.

3) If you only see `response.completed` without `done`, the client will wait
   and a UI may stall — investigate why the finisher was not emitted.

4) For multi‑turn flows (client executes tools between turns), ensure the next
   turn begins with `TOOL_CALL finalize prev` / `done prev` if the prior tool
   call hadn’t been closed in the stream.

## Notes

- Arguments are not logged in full; only `args_len` is included to reduce log
  noise and avoid leaking large payloads. Use the SSE stream or application
  traces if you need full payloads.
- In compatibility mode, the server does not wait for `/tool_outputs`; it emits
  the finisher events to keep the turn progressing for clients that run tools
  locally.

