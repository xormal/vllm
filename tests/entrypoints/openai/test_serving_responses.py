# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project

import asyncio
from collections import deque
from http import HTTPStatus
from contextlib import AsyncExitStack
from types import SimpleNamespace, MethodType
from unittest.mock import MagicMock, AsyncMock

import pytest
import pytest_asyncio
from openai.types.responses import ResponseFunctionToolCall
from openai.types.responses.tool import (
    CodeInterpreterContainerCodeInterpreterToolAuto,
    LocalShell,
    Mcp,
    Tool,
)

from vllm.entrypoints.context import (
    ConversationContext,
    StreamingHarmonyContext,
    SimpleContext,
)
from vllm.entrypoints.openai.protocol import (
    ChatCompletionToolsParam,
    ErrorInfo,
    ErrorResponse,
    FunctionDefinition,
    RequestResponseMetadata,
    ResponseCompletedEvent,
    ResponseReasoningDeltaEvent,
    ResponseToolCallDeltaEvent,
    ResponsesResponse,
    ResponsesRequest,
    ResponsesToolOutputItem,
    ResponsesToolOutputsRequest,
)
from vllm.entrypoints.openai.serving_responses import (
    OpenAIServingResponses,
    ResponseSession,
    ResponseSessionManager,
    ResponseStreamSession,
    extract_tool_types,
)
from vllm.entrypoints.openai.rate_limits import RateLimitTracker
from vllm.entrypoints.tool_server import ToolServer
from vllm.inputs.data import TokensPrompt as EngineTokensPrompt
from vllm.sampling_params import SamplingParams


class MockConversationContext(ConversationContext):
    """Mock conversation context for testing"""

    def __init__(self):
        self.init_tool_sessions_called = False
        self.init_tool_sessions_args = None
        self.init_tool_sessions_kwargs = None

    def append_output(self, output) -> None:
        pass

    def append_tool_output(self, output) -> None:
        pass

    async def call_tool(self):
        return []

    def need_builtin_tool_call(self) -> bool:
        return False

    def render_for_completion(self):
        return []

    async def init_tool_sessions(self, tool_server, exit_stack, request_id, mcp_tools):
        self.init_tool_sessions_called = True
        self.init_tool_sessions_args = (tool_server, exit_stack, request_id, mcp_tools)

    async def cleanup_session(self) -> None:
        pass


@pytest.fixture
def mock_serving_responses():
    """Create a mock OpenAIServingResponses instance"""
    serving_responses = MagicMock(spec=OpenAIServingResponses)
    serving_responses.tool_server = MagicMock(spec=ToolServer)
    return serving_responses


@pytest.fixture
def mock_context():
    """Create a mock conversation context"""
    return MockConversationContext()


@pytest.fixture
def mock_exit_stack():
    """Create a mock async exit stack"""
    return MagicMock(spec=AsyncExitStack)


def _build_serving_responses_instance(
    **kwargs,
) -> OpenAIServingResponses:
    """Create a minimal OpenAIServingResponses instance for helper tests."""

    engine_client = MagicMock()
    model_config = MagicMock()
    model_config.hf_config.model_type = "test"
    model_config.get_diff_sampling_param.return_value = {}
    model_config.is_multimodal_model = False
    engine_client.model_config = model_config
    engine_client.processor = MagicMock()
    engine_client.io_processor = MagicMock()

    models = MagicMock()
    return OpenAIServingResponses(
        engine_client=engine_client,
        models=models,
        request_logger=None,
        chat_template=None,
        chat_template_content_format="auto",
        allowed_service_tiers=["auto", "default", "flex", "scale", "priority"],
        responses_default_service_tier="auto",
        **kwargs,
    )


async def _noop_async_generator():
    if False:
        yield None


class StubStreamingContext(StreamingHarmonyContext):
    def __init__(self):
        super().__init__(messages=[], available_tools=[])
        self.appended_outputs: list = []

    def append_tool_output(self, output) -> None:
        super().append_tool_output(output)
        self.appended_outputs.append(output)

    def render_for_completion(self):
        return [1, 2, 3]


def _build_test_response_session(
    *,
    request: ResponsesRequest | None = None,
) -> ResponseSession:
    """Helper to construct a ResponseSession with sensible defaults."""

    if request is None:
        request = ResponsesRequest(model="gpt-test", input="hi", stream=True)
    sampling_params = SamplingParams(max_tokens=4)
    context = StubStreamingContext()
    tokenizer = MagicMock()
    return ResponseSession(
        id=request.request_id,
        request=request,
        sampling_params=sampling_params,
        context=context,
        model_name="gpt-test",
        tokenizer=tokenizer,
        request_metadata=RequestResponseMetadata(request_id=request.request_id),
        created_time=0,
        event_deque=deque(),
        new_event_signal=asyncio.Event(),
        generator=_noop_async_generator(),
        stream_state=None,
    )


def test_extract_tool_types(monkeypatch: pytest.MonkeyPatch) -> None:
    tools: list[Tool] = []
    assert extract_tool_types(tools) == set()

    tools.append(LocalShell(type="local_shell"))
    assert extract_tool_types(tools) == {"local_shell"}

    tools.append(CodeInterpreterContainerCodeInterpreterToolAuto(type="auto"))
    assert extract_tool_types(tools) == {"local_shell", "auto"}

    tools.extend(
        [
            Mcp(type="mcp", server_label="random", server_url=""),
            Mcp(type="mcp", server_label="container", server_url=""),
            Mcp(type="mcp", server_label="code_interpreter", server_url=""),
            Mcp(type="mcp", server_label="web_search_preview", server_url=""),
        ]
    )
    # When envs.VLLM_GPT_OSS_SYSTEM_TOOL_MCP_LABELS is not set,
    # mcp tool types are all ignored.
    assert extract_tool_types(tools) == {"local_shell", "auto"}

    # container is allowed, it would be extracted
    monkeypatch.setenv("VLLM_GPT_OSS_SYSTEM_TOOL_MCP_LABELS", "container")
    assert extract_tool_types(tools) == {"local_shell", "auto", "container"}


@pytest.mark.asyncio
async def test_tokenize_responses_counts_prompt_tokens():
    serving = _build_serving_responses_instance()
    serving.engine_client.errored = False
    serving.max_model_len = 128
    serving.use_harmony = False
    serving.default_sampling_params = {}

    request = ResponsesRequest(model="gpt-test", input="hello")

    serving._check_model = AsyncMock(return_value=None)
    serving._validate_create_responses_input = MagicMock(return_value=None)
    serving._apply_prompt_cache_key = MagicMock()
    serving._normalize_request_tools = MagicMock()
    serving._maybe_get_adapters = MagicMock(return_value=None)
    serving.models.model_name = MagicMock(return_value="gpt-test")
    serving.engine_client.get_tokenizer = AsyncMock(return_value=MagicMock())
    engine_prompt = EngineTokensPrompt(prompt_token_ids=[1, 2, 3])
    serving._make_request = AsyncMock(return_value=([], [], [engine_prompt]))
    serving._maybe_check_request_id = MagicMock(return_value=None)
    serving._validate_generator_input = MagicMock(return_value=None)
    serving._validate_request_size = MagicMock(return_value=None)

    response = await serving.tokenize_responses(request, None)

    assert isinstance(response, ResponsesResponse)
    assert response.usage.input_tokens == 3
    assert response.usage.total_tokens == 3
    assert response.usage.output_tokens == 0
    assert response.output == []

    # code_interpreter and web_search_preview are allowed,
    # they would be extracted
    monkeypatch.setenv(
        "VLLM_GPT_OSS_SYSTEM_TOOL_MCP_LABELS", "code_interpreter,web_search_preview"
    )
    assert extract_tool_types(tools) == {
        "local_shell",
        "auto",
        "code_interpreter",
        "web_search_preview",
    }


def test_normalize_request_tools_accepts_openai_schema():
    serving = _build_serving_responses_instance()
    request = ResponsesRequest(
        model="test-model",
        input="hi",
        tools=[
            ChatCompletionToolsParam(
                function=FunctionDefinition(
                    name="calculator",
                    description="basic math",
                    parameters={
                        "type": "object",
                        "properties": {
                            "a": {"type": "number"},
                            "b": {"type": "number"},
                        },
                    },
                )
            )
        ],
    )

    serving._normalize_request_tools(request)

    assert request.tools
    assert isinstance(request.tools[0], Tool)
    assert request.tools[0].name == "calculator"


def test_normalize_request_tools_preserves_non_function_types():
    serving = _build_serving_responses_instance()
    request = ResponsesRequest(
        model="test-model",
        input="hi",
        tools=[
            {"type": "local_shell"},
            {"type": "web_search"},
            {
                "type": "function",
                "function": {
                    "name": "shell",
                    "description": "execute shell commands",
                    "parameters": {
                        "type": "object",
                        "properties": {"command": {"type": "array", "items": {"type": "string"}}},
                        "required": ["command"],
                    },
                },
            },
        ],
    )

    serving._normalize_request_tools(request)

    assert [tool.type for tool in request.tools] == ["local_shell", "web_search", "function"]
    assert request.tools[-1].name == "shell"


def test_build_streaming_error_event_sequence_increment():
    serving_responses = _build_serving_responses_instance()
    error = ErrorResponse(
        error=ErrorInfo(
            message="boom",
            type="invalid_request_error",
            code=HTTPStatus.BAD_REQUEST.value,
        )
    )
    event_queue = deque([SimpleNamespace(sequence_number=4)])

    event = serving_responses._build_streaming_error_event(
        "resp_test", error, event_queue
    )

    assert event.sequence_number == 5
    assert event.response["id"] == "resp_test"
    assert event.response["status"] == "failed"
    assert event.error == error.error


def test_record_stream_event_metrics_enforces_event_size_limit():
    serving_responses = _build_serving_responses_instance(
        max_stream_event_bytes=32,
    )
    session = _build_test_response_session()
    event = ResponseReasoningDeltaEvent(
        response={"id": session.id},
        delta={"content": "x" * 64},
        sequence_number=0,
    )

    with pytest.raises(ValueError):
        serving_responses._record_stream_event_metrics(
            session,
            event,
            response_id=session.id,
        )


def test_record_stream_event_metrics_enforces_buffer_limit():
    serving_responses = _build_serving_responses_instance(
        responses_stream_buffer_max_bytes=128,
    )
    session = _build_test_response_session()
    small_event = ResponseReasoningDeltaEvent(
        response={"id": session.id},
        delta={"content": "delta"},
        sequence_number=0,
    )
    serving_responses._record_stream_event_metrics(
        session,
        small_event,
        response_id=session.id,
    )
    assert session.event_queue_bytes > 0

    large_event = ResponseReasoningDeltaEvent(
        response={"id": session.id},
        delta={"content": "y" * 256},
        sequence_number=1,
    )
    with pytest.raises(OverflowError):
        serving_responses._record_stream_event_metrics(
            session,
            large_event,
            response_id=session.id,
        )


def test_build_tool_call_delta_event():
    serving_responses = _build_serving_responses_instance()

    event = serving_responses._build_tool_call_delta_event(
        response_id="resp_123",
        tool_call_id="call_1",
        tool_name="get_weather",
        arguments_text='{"city":"SF"}',
        status="in_progress",
    )

    assert event.type == "response.tool_call.delta"
    assert event.response["id"] == "resp_123"

    chunk = event.delta
    assert isinstance(chunk, str)
    assert '"type":"tool_call"' in chunk
    assert '"call_id":"call_1"' in chunk
    assert '"city"' in chunk or "\\\"city\\\"" in chunk


def test_response_stream_session_tracks_arguments():
    request = ResponsesRequest(model="gpt-test", input="hi", stream=True)
    sampling_params = SamplingParams(max_tokens=8)
    context = StreamingHarmonyContext(messages=[], available_tools=[])
    tokenizer = MagicMock()

    session = ResponseStreamSession(
        request=request,
        sampling_params=sampling_params,
        context=context,
        model_name="gpt-test",
        tokenizer=tokenizer,
        request_metadata=RequestResponseMetadata(request_id=request.request_id),
        lora_request=None,
        trace_headers=None,
        priority=0,
        current_generator=_noop_async_generator(),
    )

    tool_call = ResponseFunctionToolCall(
        id="fc_1",
        call_id="call_1",
        type="function_call",
        name="get_weather",
        arguments="",
        status="in_progress",
    )

    session.register_tool_call("fc_1", tool_call)
    session.append_tool_call_delta("fc_1", '{"loc":"SF"}')
    session.finalize_tool_call_arguments("fc_1", '{"loc":"SF"}')

    pending = session.pending_tool_calls["call_1"]
    assert pending.tool_call.arguments == '{"loc":"SF"}'
    assert session.tool_calls_by_item_id["fc_1"] == "call_1"


@pytest.mark.asyncio
async def test_process_harmony_streams_tool_call_delta():
    serving = _build_serving_responses_instance()
    request = ResponsesRequest(model="gpt-oss", input="hi", stream=True)
    sampling_params = SamplingParams(max_tokens=8)
    tokenizer = MagicMock()

    ctx = StreamingHarmonyContext(messages=[], available_tools=[])
    ctx.parser = SimpleNamespace(
        last_content_delta='{"step": 1}',
        current_channel="commentary",
        current_recipient="functions.get_weather",
        messages=[],
    )
    ctx.is_expecting_start = lambda: False
    ctx.is_assistant_action_turn = lambda: False

    async def generator():
        yield ctx

    request_metadata = RequestResponseMetadata(request_id=request.request_id)
    session = ResponseStreamSession(
        request=request,
        sampling_params=sampling_params,
        context=ctx,
        model_name="gpt-oss",
        tokenizer=tokenizer,
        request_metadata=request_metadata,
        lora_request=None,
        trace_headers=None,
        priority=0,
        current_generator=generator(),
    )

    events: list = []

    def incr(event):
        event.sequence_number = len(events)
        events.append(event)
        return event

    async for event in serving._process_harmony_streaming_events(
        request=request,
        sampling_params=sampling_params,
        result_generator=generator(),
        context=ctx,
        model_name="gpt-oss",
        tokenizer=tokenizer,
        request_metadata=request_metadata,
        created_time=0,
        _increment_sequence_number_and_return=incr,
        session=session,
    ):
        # break after observing tool call delta to keep loop finite
        if isinstance(event, ResponseToolCallDeltaEvent):
            break

    assert any(isinstance(event, ResponseToolCallDeltaEvent) for event in events)
    tool_event = next(
        event for event in events if isinstance(event, ResponseToolCallDeltaEvent)
    )
    chunk = tool_event.delta
    assert '"call_id":"' in chunk
    assert "\\\"step\\\"" in chunk
    call_id = next(iter(session.pending_tool_calls))
    assert session.pending_tool_calls[call_id].tool_call.arguments == '{"step": 1}'


@pytest.mark.asyncio
async def test_process_harmony_streams_tool_call_delta_in_compat_mode():
    serving = _build_serving_responses_instance(compatibility_mode=True)
    request = ResponsesRequest(model="gpt-oss", input="hi", stream=True)
    sampling_params = SamplingParams(max_tokens=8)
    tokenizer = MagicMock()

    ctx = StreamingHarmonyContext(messages=[], available_tools=[])
    ctx.parser = SimpleNamespace(
        last_content_delta='{"step": 1}',
        current_channel="commentary",
        current_recipient="functions.get_weather",
        messages=[],
    )
    ctx.is_expecting_start = lambda: False
    ctx.is_assistant_action_turn = lambda: False

    async def generator():
        yield ctx

    request_metadata = RequestResponseMetadata(request_id=request.request_id)
    session = ResponseStreamSession(
        request=request,
        sampling_params=sampling_params,
        context=ctx,
        model_name="gpt-oss",
        tokenizer=tokenizer,
        request_metadata=request_metadata,
        lora_request=None,
        trace_headers=None,
        priority=0,
        current_generator=generator(),
    )

    events: list = []

    def incr(event):
        event.sequence_number = len(events)
        events.append(event)
        return event

    async def fake_await(self, session_param):
        return _noop_async_generator()

    serving._await_tool_outputs = MethodType(fake_await, serving)

    async for _ in serving._process_harmony_streaming_events(
        request=request,
        sampling_params=sampling_params,
        result_generator=generator(),
        context=ctx,
        model_name="gpt-oss",
        tokenizer=tokenizer,
        request_metadata=request_metadata,
        created_time=0,
        _increment_sequence_number_and_return=incr,
        session=session,
    ):
        pass

    assert any(isinstance(event, ResponseToolCallDeltaEvent) for event in events)


@pytest.mark.asyncio
async def test_response_session_manager_basic():
    manager = ResponseSessionManager()
    request = ResponsesRequest(model="gpt-test", input="hello", stream=True)
    sampling_params = SamplingParams(max_tokens=4)
    context = StubStreamingContext()
    tokenizer = MagicMock()
    session = ResponseSession(
        id=request.request_id,
        request=request,
        sampling_params=sampling_params,
        context=context,
        model_name="gpt-test",
        tokenizer=tokenizer,
        request_metadata=RequestResponseMetadata(request_id=request.request_id),
        created_time=0,
        event_deque=deque(),
        new_event_signal=asyncio.Event(),
        generator=_noop_async_generator(),
        stream_state=None,
    )

    manager.add_session(session)
    assert manager.get_session(session.id) is session
    removed = manager.remove_session(session.id)
    assert removed is session
    assert manager.get_session(session.id) is None


def test_response_session_manager_cleanup_expired():
    manager = ResponseSessionManager(session_ttl=0.1)
    request = ResponsesRequest(model="gpt-test", input="hi", stream=True)
    sampling_params = SamplingParams(max_tokens=4)
    context = StubStreamingContext()
    tokenizer = MagicMock()
    session = ResponseSession(
        id=request.request_id,
        request=request,
        sampling_params=sampling_params,
        context=context,
        model_name="gpt-test",
        tokenizer=tokenizer,
        request_metadata=RequestResponseMetadata(request_id=request.request_id),
        created_time=0,
        event_deque=deque(),
        new_event_signal=asyncio.Event(),
        generator=_noop_async_generator(),
        stream_state=None,
    )
    session.mark_completed()
    session.last_activity_time -= 1.0
    manager.add_session(session)
    manager.cleanup_expired_sessions()
    assert manager.get_session(session.id) is None


@pytest.mark.asyncio
async def test_handle_stream_disconnect_cancels_background_task():
    serving = _build_serving_responses_instance()
    session = _build_test_response_session()
    task = asyncio.create_task(asyncio.sleep(10))
    session.background_task = task
    serving.session_manager.add_session(session)
    serving.background_tasks[session.id] = task

    await serving.handle_stream_disconnect(session.id, reason="unit-test")

    assert serving.session_manager.get_session(session.id) is None
    assert session.id not in serving.background_tasks
    assert task.cancelled()


@pytest.mark.asyncio
async def test_retrieve_responses_stream_uses_session():
    instance = _build_serving_responses_instance()
    request = ResponsesRequest(model="test-model", input="hi", stream=True)
    sampling_params = SamplingParams(max_tokens=4)
    context = StubStreamingContext()
    tokenizer = MagicMock()
    response_payload = ResponsesResponse.from_request(
        request,
        sampling_params,
        model_name="test-model",
        created_time=0,
        output=[],
        status="completed",
        usage=None,
    )
    completed_event = ResponseCompletedEvent(
        type="response.completed",
        sequence_number=0,
        response=response_payload,
    )
    session = ResponseSession(
        id=request.request_id,
        request=request,
        sampling_params=sampling_params,
        context=context,
        model_name="test-model",
        tokenizer=tokenizer,
        request_metadata=RequestResponseMetadata(request_id=request.request_id),
        created_time=0,
        event_deque=deque([completed_event]),
        new_event_signal=asyncio.Event(),
        generator=_noop_async_generator(),
        stream_state=None,
    )
    session.mark_completed()
    instance.session_manager.add_session(session)

    generator = await instance.retrieve_responses(
        session.id,
        starting_after=None,
        stream=True,
    )
    events = []
    async for event in generator:
        events.append(event)
    assert events
    assert events[0].type == "response.completed"


@pytest.mark.asyncio
async def test_retrieve_responses_stream_not_found_without_session():
    instance = _build_serving_responses_instance()
    response = await instance.retrieve_responses(
        "resp_missing",
        starting_after=None,
        stream=True,
    )
    assert isinstance(response, ErrorResponse)
    assert response.error.code == HTTPStatus.NOT_FOUND.value


@pytest.mark.asyncio
async def test_list_response_input_items_returns_items():
    instance = _build_serving_responses_instance()
    request = ResponsesRequest(
        model="test-model",
        input=[
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Hello"}],
            },
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "input_text", "text": "Ack"}],
            },
        ],
        store=True,
    )
    await instance._record_input_items(request)
    sampling_params = SamplingParams(max_tokens=4)
    response = ResponsesResponse.from_request(
        request,
        sampling_params,
        model_name="test-model",
        created_time=0,
        output=[],
        status="completed",
        usage=None,
    )
    await instance._store_response_object(response)
    result = await instance.list_response_input_items(
        response.id,
        limit=10,
        order="asc",
        after=None,
        include=None,
    )
    assert not isinstance(result, ErrorResponse)
    payload, user_id = result
    assert user_id == request.user
    assert payload["object"] == "list"
    assert len(payload["data"]) == 2
    assert payload["data"][0]["content"][0]["text"] == "Hello"


def test_normalize_input_items_handles_unpickleable_values():
    class Unpickleable:
        def __reduce_ex__(self, _protocol: int):
            raise TypeError("no pickle")

    instance = _build_serving_responses_instance()
    normalized = instance._normalize_input_items(
        [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Hello"}],
                "extra": Unpickleable(),
            }
        ]
    )

    assert normalized
    assert normalized[0]["role"] == "user"
    assert normalized[0]["content"][0]["text"] == "Hello"
    assert "id" in normalized[0]


@pytest.mark.asyncio
async def test_list_response_input_items_errors_on_missing_after():
    instance = _build_serving_responses_instance()
    request = ResponsesRequest(
        model="test-model",
        input=[
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Hello"}],
                "id": "msg_existing",
            }
        ],
        store=True,
    )
    await instance._record_input_items(request)
    sampling_params = SamplingParams(max_tokens=4)
    response = ResponsesResponse.from_request(
        request,
        sampling_params,
        model_name="test-model",
        created_time=0,
        output=[],
        status="completed",
        usage=None,
    )
    await instance._store_response_object(response)
    result = await instance.list_response_input_items(
        response.id,
        limit=5,
        order="desc",
        after="unknown",
        include=None,
    )
    assert isinstance(result, ErrorResponse)
    assert result.error.code == HTTPStatus.BAD_REQUEST.value


@pytest.mark.asyncio
async def test_create_responses_rate_limited():
    instance = _build_serving_responses_instance()
    request = ResponsesRequest(model="test-model", input="hi")
    instance.rate_limiter = MagicMock()
    instance.enforce_rate_limits = True
    instance.rate_limit_events_enabled = False
    instance.rate_limiter.check_and_reserve = AsyncMock(return_value=(False, 2.5))

    error = await instance.create_responses(request, raw_request=None)
    assert isinstance(error, ErrorResponse)
    assert error.error.code == HTTPStatus.TOO_MANY_REQUESTS.value
    assert error.retry_after == 2.5


@pytest.mark.asyncio
async def test_responses_stream_generator_emits_incomplete_event():
    instance = _build_serving_responses_instance()
    request = ResponsesRequest(model="test-model", input="hi", stream=True)
    sampling_params = SamplingParams(max_tokens=4)
    context = SimpleContext()
    tokenizer = MagicMock()
    request_metadata = RequestResponseMetadata(request_id=request.request_id)

    async def empty_processer(*args, **kwargs):
        if False:
            yield None

    instance._process_simple_streaming_events = empty_processer  # type: ignore
    incomplete_response = ResponsesResponse.from_request(
        request,
        sampling_params,
        model_name="test-model",
        created_time=0,
        output=[],
        status="incomplete",
        usage=None,
    )
    instance.responses_full_generator = AsyncMock(return_value=incomplete_response)

    events = []
    async for event in instance.responses_stream_generator(
        request,
        sampling_params,
        _noop_async_generator(),
        context,
        "test-model",
        tokenizer,
        request_metadata,
    ):
        events.append(event)
        if event.type == "response.incomplete":
            break

    event_types = [event.type for event in events]
    assert "response.queued" in event_types
    assert "response.incomplete" in event_types


def test_validate_include_message_input_image_error():
    instance = _build_serving_responses_instance()
    request = ResponsesRequest(
        model="test-model",
        input="hello",
        include=["message.input_image.image_url"],
    )
    error = instance._validate_create_responses_input(request)
    assert isinstance(error, ErrorResponse)
    assert error.error.code == HTTPStatus.BAD_REQUEST.value


def test_validate_include_computer_call_flag():
    instance = _build_serving_responses_instance()
    request = ResponsesRequest(
        model="test-model",
        input="hello",
        include=["computer_call_output.output.image_url"],
    )
    error = instance._validate_create_responses_input(request)
    assert isinstance(error, ErrorResponse)
    assert error.error.code == HTTPStatus.BAD_REQUEST.value

    enabled_instance = _build_serving_responses_instance(enable_computer_call=True)
    ok = enabled_instance._validate_create_responses_input(request)
    assert ok is None


def test_build_web_search_sources_event_returns_payload():
    instance = _build_serving_responses_instance()
    request = ResponsesRequest(
        model="test-model",
        input="hello",
        include=["web_search_call.action.sources"],
    )
    event = instance._build_web_search_sources_event(  # type: ignore[attr-defined]
        request,
        response_id="resp_test",
        item_id="tool_123",
        function_name="search",
        parsed_args={"query": "vllm", "sources": [{"title": "docs", "url": "https://vllm.ai"}]},
    )
    assert event is not None
    assert event.context["web_search_call.action.sources"][0]["sources"] == [
        {"title": "docs", "url": "https://vllm.ai"}
    ]


def test_request_body_bytes_limit():
    instance = _build_serving_responses_instance(max_request_body_bytes=10)
    request = ResponsesRequest(model="test-model", input="hello world")
    error = instance._validate_create_responses_input(request)
    assert isinstance(error, ErrorResponse)


def test_store_requires_enabled():
    instance = _build_serving_responses_instance(disable_responses_store=True)
    request = ResponsesRequest(model="test-model", input="hi", store=True)
    error = instance._validate_create_responses_input(request)
    assert isinstance(error, ErrorResponse)


def test_background_requires_store_true():
    instance = _build_serving_responses_instance()
    request = ResponsesRequest(
        model="test-model", input="hi", background=True, store=False
    )
    error = instance._validate_create_responses_input(request)
    assert isinstance(error, ErrorResponse)


@pytest.mark.asyncio
async def test_store_response_roundtrip():
    instance = _build_serving_responses_instance()
    request = ResponsesRequest(model="test-model", input="hi")
    sampling = SamplingParams(max_tokens=4)
    response = ResponsesResponse.from_request(
        request,
        sampling,
        model_name="test-model",
        created_time=0,
        output=[],
        status="completed",
        usage=None,
    )
    await instance._store_response_object(response)
    stored = await instance._get_stored_response(response.id)
    assert stored is response


def test_responses_response_includes_seed():
    request = ResponsesRequest(model="test-model", input="hi", seed=42)
    sampling = request.to_sampling_params(default_max_tokens=4)

    response = ResponsesResponse.from_request(
        request,
        sampling,
        model_name="test-model",
        created_time=0,
        output=[],
        status="completed",
        usage=None,
    )

    assert response.seed == 42


@pytest.mark.asyncio
async def test_store_response_ttl_eviction():
    instance = _build_serving_responses_instance(responses_store_ttl=0.1)
    request = ResponsesRequest(model="test-model", input="hi")
    sampling = SamplingParams(max_tokens=4)
    resp1 = ResponsesResponse.from_request(
        request,
        sampling,
        model_name="test-model",
        created_time=0,
        output=[],
        status="completed",
        usage=None,
    )
    await instance._store_response_object(resp1)
    instance.response_store_expirations[resp1.id] -= 1.0
    resp2 = ResponsesResponse.from_request(
        request,
        sampling,
        model_name="test-model",
        created_time=1,
        output=[],
        status="completed",
        usage=None,
    )
    await instance._store_response_object(resp2)
    assert await instance._get_stored_response(resp1.id) is None


@pytest.mark.asyncio
async def test_store_response_max_entries():
    instance = _build_serving_responses_instance(responses_store_max_entries=1)
    request = ResponsesRequest(model="test-model", input="hi")
    sampling = SamplingParams(max_tokens=4)
    resp1 = ResponsesResponse.from_request(
        request,
        sampling,
        model_name="test-model",
        created_time=0,
        output=[],
        status="completed",
        usage=None,
    )
    resp2 = ResponsesResponse.from_request(
        request,
        sampling,
        model_name="test-model",
        created_time=1,
        output=[],
        status="completed",
        usage=None,
    )
    await instance._store_response_object(resp1)
    await instance._store_response_object(resp2)
    stored1 = await instance._get_stored_response(resp1.id)
    stored2 = await instance._get_stored_response(resp2.id)
    assert stored1 is None
    assert stored2 is resp2


@pytest.mark.asyncio
async def test_submit_tool_outputs_rejects_unexpected_call():
    instance = _build_serving_responses_instance()
    request = ResponsesRequest(model="test-model", input="hi", stream=True)
    sampling_params = SamplingParams(max_tokens=4)
    context = StubStreamingContext()
    tokenizer = MagicMock()
    stream_state = ResponseStreamSession(
        request=request,
        sampling_params=sampling_params,
        context=context,
        model_name="test-model",
        tokenizer=tokenizer,
        request_metadata=RequestResponseMetadata(request_id=request.request_id),
        lora_request=None,
        trace_headers=None,
        priority=0,
        current_generator=_noop_async_generator(),
    )
    session = ResponseSession(
        id=request.request_id,
        request=request,
        sampling_params=sampling_params,
        context=context,
        model_name="test-model",
        tokenizer=tokenizer,
        request_metadata=RequestResponseMetadata(request_id=request.request_id),
        created_time=0,
        event_deque=deque(),
        new_event_signal=asyncio.Event(),
        generator=_noop_async_generator(),
        stream_state=stream_state,
        user_id="user-test",
    )
    instance.session_manager.add_session(session)
    tool_call = ResponseFunctionToolCall(
        id="fc_1",
        call_id="call_1",
        type="function_call",
        name="echo",
        arguments="{}",
        status="in_progress",
    )
    stream_state.register_tool_call("fc_1", tool_call)
    stream_state.waiting_for_tool_outputs = False
    payload = ResponsesToolOutputsRequest(
        tool_call_id="call_1",
        output=[ResponsesToolOutputItem(text="ok")],
    )
    error = await instance.submit_tool_outputs(request.request_id, payload)
    assert isinstance(error, ErrorResponse)


@pytest.mark.asyncio
async def test_tool_outputs_payload_limit():
    instance = _build_serving_responses_instance(max_tool_output_bytes=10)
    request = ResponsesRequest(model="test-model", input="hi", stream=True)
    sampling_params = SamplingParams(max_tokens=4)
    context = StubStreamingContext()
    tokenizer = MagicMock()
    stream_state = ResponseStreamSession(
        request=request,
        sampling_params=sampling_params,
        context=context,
        model_name="test-model",
        tokenizer=tokenizer,
        request_metadata=RequestResponseMetadata(request_id=request.request_id),
        lora_request=None,
        trace_headers=None,
        priority=0,
        current_generator=_noop_async_generator(),
    )
    stream_state.register_tool_call(
        "fc_1",
        ResponseFunctionToolCall(
            id="fc_1",
            call_id="call_1",
            type="function_call",
            name="echo",
            arguments="{}",
            status="in_progress",
        ),
    )
    stream_state.waiting_for_tool_outputs = True
    session = ResponseSession(
        id=request.request_id,
        request=request,
        sampling_params=sampling_params,
        context=context,
        model_name="test-model",
        tokenizer=tokenizer,
        request_metadata=RequestResponseMetadata(request_id=request.request_id),
        created_time=0,
        event_deque=deque(),
        new_event_signal=asyncio.Event(),
        generator=_noop_async_generator(),
        stream_state=stream_state,
        user_id="user",
    )
    instance.session_manager.add_session(session)

    payload = ResponsesToolOutputsRequest(
        tool_call_id="call_1",
        output=[
            ResponsesToolOutputItem(text="01234567890"),
        ],
    )
    error = await instance.submit_tool_outputs(request.request_id, payload)
    assert isinstance(error, ErrorResponse)


class TestInitializeToolSessions:
    """Test class for _initialize_tool_sessions method"""

    @pytest_asyncio.fixture
    async def serving_responses_instance(self):
        """Create a real OpenAIServingResponses instance for testing"""
        # Create minimal mocks for required dependencies
        engine_client = MagicMock()

        model_config = MagicMock()
        model_config.hf_config.model_type = "test"
        model_config.get_diff_sampling_param.return_value = {}
        engine_client.model_config = model_config

        engine_client.processor = MagicMock()
        engine_client.io_processor = MagicMock()

        models = MagicMock()

        tool_server = MagicMock(spec=ToolServer)

        # Create the actual instance
        instance = OpenAIServingResponses(
            engine_client=engine_client,
            models=models,
            request_logger=None,
            chat_template=None,
            chat_template_content_format="auto",
            tool_server=tool_server,
        )

        return instance

    @pytest.mark.asyncio
    async def test_initialize_tool_sessions(
        self, serving_responses_instance, mock_context, mock_exit_stack
    ):
        """Test that method works correctly with only MCP tools"""

        request = ResponsesRequest(input="test input", tools=[])

        # Call the method
        await serving_responses_instance._initialize_tool_sessions(
            request, mock_context, mock_exit_stack
        )
        assert mock_context.init_tool_sessions_called is False

        # Create only MCP tools
        tools = [
            {"type": "web_search_preview"},
            {"type": "code_interpreter", "container": {"type": "auto"}},
        ]

        request = ResponsesRequest(input="test input", tools=tools)

        # Call the method
        await serving_responses_instance._initialize_tool_sessions(
            request, mock_context, mock_exit_stack
        )

        # Verify that init_tool_sessions was called
        assert mock_context.init_tool_sessions_called


@pytest.mark.asyncio
async def test_submit_tool_outputs_resumes_session(monkeypatch: pytest.MonkeyPatch):
    serving = _build_serving_responses_instance()
    request = ResponsesRequest(model="test-model", input="hi")
    sampling_params = SamplingParams(max_tokens=16)
    context = StubStreamingContext()
    tokenizer = MagicMock()
    metadata = RequestResponseMetadata(request_id=request.request_id)
    session = ResponseStreamSession(
        request=request,
        sampling_params=sampling_params,
        context=context,
        model_name="test-model",
        tokenizer=tokenizer,
        request_metadata=metadata,
        lora_request=None,
        trace_headers=None,
        priority=0,
        current_generator=_noop_async_generator(),
    )
    tool_call = ResponseFunctionToolCall(
        id="item_1",
        call_id="call_1",
        type="function_call",
        name="get_weather",
        arguments="{}",
        status="in_progress",
    )
    session.register_tool_call("item_1", tool_call)
    session.waiting_for_tool_outputs = True
    serving.response_sessions[request.request_id] = session

    async def _fake_generator():
        if False:
            yield None

    monkeypatch.setattr(
        serving,
        "_generate_with_builtin_tools",
        lambda *args, **kwargs: _fake_generator(),
    )

    payload = ResponsesToolOutputsRequest(
        tool_call_id="call_1",
        output=[ResponsesToolOutputItem(text="Sunny")],
    )

    result = await serving.submit_tool_outputs(request.request_id, payload)

    assert result == {"id": request.request_id, "status": "in_progress"}
    assert len(context.appended_outputs) == 1
    assert not session.pending_tool_calls
    assert session.resume_event.is_set()

    def test_validate_create_responses_input(
        self, serving_responses_instance, mock_context, mock_exit_stack
    ):
        request = ResponsesRequest(
            input="test input",
            previous_input_messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "What is my horoscope? I am an Aquarius.",
                        }
                    ],
                }
            ],
            previous_response_id="lol",
        )
        error = serving_responses_instance._validate_create_responses_input(request)
        assert error is not None
        assert error.error.type == "invalid_request_error"


class TestValidateGeneratorInput:
    """Test class for _validate_generator_input method"""

    @pytest_asyncio.fixture
    async def serving_responses_instance(self):
        """Create a real OpenAIServingResponses instance for testing"""
        # Create minimal mocks for required dependencies
        engine_client = MagicMock()

        model_config = MagicMock()
        model_config.hf_config.model_type = "test"
        model_config.get_diff_sampling_param.return_value = {}
        engine_client.model_config = model_config

        engine_client.processor = MagicMock()
        engine_client.io_processor = MagicMock()

        models = MagicMock()

        # Create the actual instance
        instance = OpenAIServingResponses(
            engine_client=engine_client,
            models=models,
            request_logger=None,
            chat_template=None,
            chat_template_content_format="auto",
        )

        # Set max_model_len for testing
        instance.max_model_len = 100

        return instance

    def test_validate_generator_input(self, serving_responses_instance):
        """Test _validate_generator_input with valid prompt length"""
        # Create an engine prompt with valid length (less than max_model_len)
        valid_prompt_token_ids = list(range(5))  # 5 tokens < 100 max_model_len
        engine_prompt = EngineTokensPrompt(prompt_token_ids=valid_prompt_token_ids)

        # Call the method
        result = serving_responses_instance._validate_generator_input(engine_prompt)

        # Should return None for valid input
        assert result is None

        # create an invalid engine prompt
        invalid_prompt_token_ids = list(range(200))  # 100 tokens >= 100 max_model_len
        engine_prompt = EngineTokensPrompt(prompt_token_ids=invalid_prompt_token_ids)

        # Call the method
        result = serving_responses_instance._validate_generator_input(engine_prompt)

        # Should return an ErrorResponse
        assert result is not None
        assert isinstance(result, ErrorResponse)


class TestReasoningSummaryEvents:
    def test_summary_events_emitted(self):
        instance = _build_serving_responses_instance()
        events = instance._generate_reasoning_summary_events(
            response_id="resp_123",
            reasoning_text="In conclusion, value is 42. Therefore, return 42.",
            item_id="rs_1",
            output_index=0,
        )
        assert len(events) >= 2
        assert events[0].type == "response.reasoning.summary.added"
        assert events[1].type == "response.reasoning.summary.delta"
        assert "summary" in events[1].delta
        event_types = [event.type for event in events]
        assert "response.reasoning_summary_text.delta" in event_types
        assert "response.reasoning_summary_text.done" in event_types
        assert "response.reasoning_summary_part.added" in event_types
        assert "response.reasoning_summary_part.done" in event_types

    def test_summary_events_skipped_for_empty_reasoning(self):
        instance = _build_serving_responses_instance()
        events = instance._generate_reasoning_summary_events(
            response_id="resp_123",
            reasoning_text="   ",
            item_id="rs_1",
            output_index=0,
        )
        assert events == []


class TestAdditionalContextEvents:
    def test_additional_context_event_emitted(self):
        instance = _build_serving_responses_instance()
        request = ResponsesRequest(
            input="hello",
            include=["reasoning.encrypted_content"],
        )
        events = instance._generate_additional_context_events(
            request,
            response_id="resp_123",
            reasoning_text="Working through multi-step reasoning.",
        )
        assert len(events) == 1
        event = events[0]
        assert event.type == "response.additional_context"
        assert "reasoning.encrypted_content" in event.context

    def test_additional_context_event_skipped_without_include(self):
        instance = _build_serving_responses_instance()
        request = ResponsesRequest(input="hello")
        events = instance._generate_additional_context_events(
            request,
            response_id="resp_123",
            reasoning_text="Working through multi-step reasoning.",
        )
        assert events == []


class TestRateLimitTracker:
    @pytest.mark.asyncio
    async def test_tracker_records_usage(self):
        tracker = RateLimitTracker(
            requests_per_minute=10,
            requests_per_hour=20,
            tokens_per_minute=100,
        )
        await tracker.record_request("user-1")
        await tracker.record_tokens("user-1", 50)
        payload = await tracker.build_rate_limit_payload("user-1")
        assert "primary" in payload
        assert payload["primary"].limit_type == "primary"
        assert payload["tokens"].limit_type == "tokens"
        assert payload["tokens"].used_percent > 0.0


class TestPromptCacheKey:
    def test_prompt_cache_key_sets_cache_salt(self):
        instance = _build_serving_responses_instance()
        request = ResponsesRequest(model="test", input="hi", prompt_cache_key="key123")
        assert request.cache_salt is None
        instance._apply_prompt_cache_key(request)
        assert request.cache_salt == "key123"

    def test_prompt_cache_key_respects_existing_cache_salt(self, caplog):
        instance = _build_serving_responses_instance()
        request = ResponsesRequest(model="test", input="hi", prompt_cache_key="key123")
        request.cache_salt = "existing"
        with caplog.at_level("WARNING"):
            instance._apply_prompt_cache_key(request)
        assert request.cache_salt == "existing"
        assert "prompt_cache_key" in caplog.text


def test_compat_mode_rejects_extra_fields():
    instance = _build_serving_responses_instance(compatibility_mode=True)
    request = ResponsesRequest(
        model="test-model",
        input="hi",
        mm_processor_kwargs={"foo": "bar"},
    )
    error = instance._validate_create_responses_input(request)
    assert isinstance(error, ErrorResponse)
    assert error.error.type == "invalid_request_error"


def test_compat_mode_rejects_non_allowlisted_include():
    compat_instance = _build_serving_responses_instance(compatibility_mode=True)
    regular_instance = _build_serving_responses_instance()
    request = ResponsesRequest(
        model="test-model",
        input="hi",
        include=["message.output_text.logprobs"],
    )
    assert (
        regular_instance._validate_create_responses_input(request) is None
    )
    compat_error = compat_instance._validate_create_responses_input(request)
    assert isinstance(compat_error, ErrorResponse)


def test_request_id_mismatch_returns_error():
    instance = _build_serving_responses_instance()
    request = ResponsesRequest(model="test-model", input="hi")
    error = instance._maybe_check_request_id("header-id", request)
    assert isinstance(error, ErrorResponse)
    assert "mismatch" in error.error.message


def test_request_id_match_allows_processing():
    instance = _build_serving_responses_instance()
    request = ResponsesRequest(model="test-model", input="hi")
    error = instance._maybe_check_request_id(request.request_id, request)
    assert error is None


def test_service_tier_defaults_to_config():
    instance = _build_serving_responses_instance(
        responses_default_service_tier="priority",
        allowed_service_tiers=["auto", "default", "priority"],
    )
    request = ResponsesRequest(model="test", input="hi", service_tier="auto")
    error = instance._validate_create_responses_input(request)
    assert error is None
    assert request.service_tier == "priority"


def test_service_tier_rejects_disallowed_value():
    instance = _build_serving_responses_instance(
        allowed_service_tiers=["auto", "default"]
    )
    request = ResponsesRequest(model="test", input="hi", service_tier="scale")
    error = instance._validate_create_responses_input(request)
    assert isinstance(error, ErrorResponse)


class TestBuiltInToolEventBuilders:
    def test_file_search_call_events(self):
        instance = _build_serving_responses_instance()
        events = instance._build_file_search_call_events(
            item_id="fs_1",
            output_index=0,
        )
        event_types = [event.type for event in events]
        assert event_types == [
            "response.file_search_call.in_progress",
            "response.file_search_call.searching",
            "response.file_search_call.completed",
        ]

    def test_image_generation_call_events_with_partial(self):
        instance = _build_serving_responses_instance()
        events = instance._build_image_generation_call_events(
            item_id="img_1",
            output_index=0,
            partial_image_b64="...",
        )
        event_types = [event.type for event in events]
        assert "response.image_generation_call.partial_image" in event_types
        assert event_types[0] == "response.image_generation_call.in_progress"


class TestImageToolGating:
    def test_requires_multimodal_or_config(self):
        instance = _build_serving_responses_instance()
        instance.model_config.is_multimodal_model = False
        with pytest.raises(RuntimeError):
            instance._require_image_tools_enabled("image_generation.generate")

        config = {
            "provider": "demo-image-backend",
            "api_base": "https://images.example.com/v1",
            "api_key_env": "EXAMPLE_IMAGE_KEY",
            "default_model": "demo-image",
        }
        instance_with_config = _build_serving_responses_instance(
            image_service_config=config
        )
        instance_with_config.model_config.is_multimodal_model = False
        instance_with_config._require_image_tools_enabled("image_generation.generate")

        multimodal_instance = _build_serving_responses_instance()
        multimodal_instance.model_config.is_multimodal_model = True
        multimodal_instance._require_image_tools_enabled("images.edit")

    def test_image_service_config_validation(self):
        with pytest.raises(ValueError):
            _build_serving_responses_instance(
                image_service_config={"provider": "missing-fields"}
            )
