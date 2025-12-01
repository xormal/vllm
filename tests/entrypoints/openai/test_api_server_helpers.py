# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project

import asyncio
import json
from http import HTTPStatus
from types import SimpleNamespace

import pytest
from types import SimpleNamespace

from vllm.entrypoints.openai import api_server
from vllm.entrypoints.openai.protocol import ErrorInfo, ErrorResponse


def test_attach_item_ids_adds_missing_ids():
    items = [{"role": "user", "content": "hi"}, {"id": "existing", "role": "assistant"}]
    result = api_server._attach_item_ids(items.copy())  # type: ignore[attr-defined]
    assert result[0]["id"].startswith("item_0_")
    assert result[1]["id"] == "existing"


def test_attach_item_ids_sets_attribute():
    obj = SimpleNamespace(role="user", id=None)
    result = api_server._attach_item_ids([obj])  # type: ignore[attr-defined]
    assert isinstance(result[0].id, str)
    assert result[0].id.startswith("item_0_")


def test_json_error_response_sets_retry_after_header():
    error = ErrorResponse(
        error=ErrorInfo(
            message="rate limit",
            type="rate_limit_error",
            code=HTTPStatus.TOO_MANY_REQUESTS.value,
        )
    )
    response = api_server._json_error_response(error)  # type: ignore[attr-defined]
    assert response.headers["Retry-After"] == "1"


@pytest.mark.asyncio
async def test_stream_error_response_emits_event():
    error = ErrorResponse(
        error=ErrorInfo(
            message="boom",
            type="invalid_request_error",
            code=400,
        )
    )
    response = api_server._stream_error_response(error, request_id="resp_test")  # type: ignore[attr-defined]
    assert response.media_type == "text/event-stream"
    body = b""
    async for chunk in response.body_iterator:
        body += chunk
    body_text = body.decode()
    assert "event: response.error" in body_text
    assert '"status": "failed"' in body_text
    assert '"id": "resp_test"' in body_text


def test_stream_error_response_sets_retry_after_header():
    error = ErrorResponse(
        error=ErrorInfo(
            message="over quota",
            type="rate_limit_error",
            code=HTTPStatus.TOO_MANY_REQUESTS.value,
        )
    )
    response = api_server._stream_error_response(error, request_id="resp_test")  # type: ignore[attr-defined]
    assert response.headers["Retry-After"] == "1"


def test_sse_decoder_handles_malformed_chunks():
    decoder = api_server.SSEDecoder()  # type: ignore[attr-defined]
    assert decoder.decode_chunk(b"\xff\xfe") == []
    assert decoder.decode_chunk(b"event: response\n") == []
    events = decoder.decode_chunk(b"data: {\"a\": 1}\n\n")
    assert len(events) == 1 and events[0]["type"] == "data"
    events = decoder.decode_chunk(b"data: [DONE]\n\n")
    assert events and events[0]["type"] == "done"


def test_sse_event_validator_accepts_known_event():
    validator = api_server.SSEEventValidator()  # type: ignore[attr-defined]
    validator.validate(
        "response.created",
        {"type": "response.created", "sequence_number": 0},
    )
    validator.validate(
        "response.queued",
        {"type": "response.queued", "sequence_number": 1},
    )
    validator.validate(
        "response.incomplete",
        {"type": "response.incomplete", "sequence_number": 2},
    )
    validator.validate(
        "response.reasoning_summary_text.delta",
        {
            "type": "response.reasoning_summary_text.delta",
            "sequence_number": 3,
        },
    )
    validator.validate(
        "response.file_search_call.in_progress",
        {"type": "response.file_search_call.in_progress", "sequence_number": 4},
    )
    validator.validate(
        "response.image_generation_call.in_progress",
        {"type": "response.image_generation_call.in_progress", "sequence_number": 5},
    )


def test_sse_event_validator_rejects_invalid_type():
    validator = api_server.SSEEventValidator()  # type: ignore[attr-defined]
    with pytest.raises(api_server.SSEValidationError):  # type: ignore[attr-defined]
        validator.validate(
            "response\nbad",
            {"type": "response\nbad", "sequence_number": 0},
        )


def test_sse_event_validator_accepts_function_call_argument_events():
    validator = api_server.SSEEventValidator()  # type: ignore[attr-defined]
    validator.validate(
        "response.function_call_arguments.delta",
        {"type": "response.function_call_arguments.delta", "sequence_number": 3},
    )
    validator.validate(
        "response.function_call_arguments.done",
        {"type": "response.function_call_arguments.done", "sequence_number": 4},
    )


def test_sse_chunk_buffer_flush_threshold():
    chunker = api_server.SSEChunkBuffer(max_bytes=10)  # type: ignore[attr-defined]
    assert chunker.append("12345") == []
    flushed = chunker.append("67890")
    assert flushed  # size >= 10 triggers flush
    assert "".join(flushed) == "1234567890"
    assert chunker.flush() == []


def test_sse_chunk_buffer_manual_flush():
    chunker = api_server.SSEChunkBuffer(max_bytes=50)  # type: ignore[attr-defined]
    chunker.append("abc")
    chunker.append("def")
    flushed = chunker.flush()
    assert flushed == ["abcdef"]
    assert chunker.flush() == []


@pytest.mark.asyncio
async def test_convert_stream_to_sse_events_triggers_disconnect_cleanup():
    class DummyEvent:
        type = "response.completed"

        def model_dump(self, exclude_none=True):
            return {"type": self.type, "response": {"id": "resp_test"}}

        def model_dump_json(self, indent=None):
            return json.dumps(self.model_dump())

    disconnect_called = asyncio.Event()

    async def disconnect():
        disconnect_called.set()

    async def source():
        try:
            while True:
                yield DummyEvent()
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            raise

    agen = api_server._convert_stream_to_sse_events(  # type: ignore[attr-defined]
        source(),
        on_disconnect=disconnect,
    )

    first_chunk = await agen.__anext__()
    assert "event: response.completed" in first_chunk

    inflight = asyncio.create_task(agen.__anext__())
    await asyncio.sleep(0)
    inflight.cancel()
    with pytest.raises(asyncio.CancelledError):
        await inflight

    await asyncio.wait_for(disconnect_called.wait(), timeout=0.2)
    await agen.aclose()


@pytest.mark.asyncio
async def test_convert_stream_to_sse_events_emits_error_on_validation_failure():
    class BadEvent:
        type = "response\nbad"

        def model_dump(self, exclude_none=True):
            return {"type": self.type, "response": {"id": "resp_bad"}}

    async def source():
        yield BadEvent()

    agen = api_server._convert_stream_to_sse_events(  # type: ignore[attr-defined]
        source()
    )
    chunk = await agen.__anext__()
    assert "event: response.error" in chunk
    assert "stream_validation_error" in chunk
    with pytest.raises(StopAsyncIteration):
        await agen.__anext__()


@pytest.mark.asyncio
async def test_convert_stream_to_sse_events_emits_ping():
    class DummyEvent:
        def __init__(self, event_type: str):
            self.type = event_type

        def model_dump(self, exclude_none=True):
            return {"type": self.type, "response": {"id": "resp_ping"}}

    async def source():
        yield DummyEvent("response.created")
        await asyncio.sleep(0.05)
        yield DummyEvent("response.completed")

    agen = api_server._convert_stream_to_sse_events(  # type: ignore[attr-defined]
        source(),
        ping_interval=0.01,
    )
    chunks = []
    try:
        while True:
            chunks.append(await agen.__anext__())
    except StopAsyncIteration:
        pass
    assert any("event: response.ping" in chunk for chunk in chunks)


@pytest.mark.asyncio
async def test_convert_stream_to_sse_events_preserves_sequence_numbers():
    class DummyEvent:
        def __init__(self, event_type: str, sequence_number: int):
            self.type = event_type
            self.sequence_number = sequence_number

        def model_dump(self, exclude_none=True):
            return {
                "type": self.type,
                "sequence_number": self.sequence_number,
                "response": {"id": "resp_seq"},
            }

    async def source():
        yield DummyEvent("response.created", 5)
        yield DummyEvent("response.completed", 6)

    agen = api_server._convert_stream_to_sse_events(  # type: ignore[attr-defined]
        source()
    )
    chunk1 = await agen.__anext__()
    chunk2 = await agen.__anext__()
    assert '"sequence_number":5' in chunk1
    assert '"sequence_number":6' in chunk2
    done_chunk = await agen.__anext__()
    assert done_chunk.strip() == "data: [DONE]"


@pytest.mark.asyncio
async def test_convert_stream_to_sse_events_applies_reasoning_shims():
    class ReasoningDelta:
        type = "response.reasoning.delta"

        def __init__(self, content: str):
            self._content = content

        def model_dump(self, exclude_none=True):
            return {
                "type": self.type,
                "delta": {"content": self._content},
                "response": {"id": "resp_reasoning"},
            }

    class ReasoningDone:
        type = "response.reasoning.done"

        def __init__(self, content: str):
            self._content = content

        def model_dump(self, exclude_none=True):
            return {
                "type": self.type,
                "reasoning": {"content": self._content},
                "response": {"id": "resp_reasoning"},
            }

    class ReasoningSummaryDelta:
        type = "response.reasoning.summary.delta"

        def __init__(self, summary: str):
            self._summary = summary

        def model_dump(self, exclude_none=True):
            return {
                "type": self.type,
                "delta": {"summary": self._summary},
                "response": {"id": "resp_reasoning"},
            }

    class Completed:
        type = "response.completed"

        def model_dump(self, exclude_none=True):
            return {"type": self.type, "response": {"id": "resp_reasoning"}}

    async def source():
        yield ReasoningDelta("step 1")
        yield ReasoningDone("final reasoning block")
        yield ReasoningSummaryDelta("summary chunk")
        yield Completed()

    agen = api_server._convert_stream_to_sse_events(  # type: ignore[attr-defined]
        source(),
        compatibility_mode=True,
    )

    chunks: list[str] = []
    try:
        while True:
            chunks.append(await agen.__anext__())
    except StopAsyncIteration:
        pass

    delta_chunk = next(
        chunk for chunk in chunks if "event: response.reasoning.delta" in chunk
    )
    assert '"delta":"step 1"' in delta_chunk

    done_chunk = next(
        chunk for chunk in chunks if "event: response.reasoning.done" in chunk
    )
    assert '"reasoning":"final reasoning block"' in done_chunk

    summary_chunk = next(
        chunk
        for chunk in chunks
        if "event: response.reasoning.summary.delta" in chunk
    )
    assert '"delta":"summary chunk"' in summary_chunk


@pytest.mark.asyncio
async def test_convert_stream_to_sse_events_leaves_reasoning_objects_in_default_mode():
    class ReasoningDelta:
        type = "response.reasoning.delta"

        def __init__(self, content: str):
            self._content = content

        def model_dump(self, exclude_none=True):
            return {
                "type": self.type,
                "delta": {"content": self._content},
                "response": {"id": "resp_reasoning"},
            }

    class Completed:
        type = "response.completed"

        def model_dump(self, exclude_none=True):
            return {"type": self.type, "response": {"id": "resp_reasoning"}}

    async def source():
        yield ReasoningDelta("original payload")
        yield Completed()

    agen = api_server._convert_stream_to_sse_events(  # type: ignore[attr-defined]
        source(),
        compatibility_mode=False,
    )

    first_chunk = await agen.__anext__()
    assert '"delta":{"content":"original payload"}' in first_chunk
