# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project

from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
import time
import uuid
from collections import deque
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Sequence
from contextlib import AsyncExitStack
from copy import copy, deepcopy
from dataclasses import dataclass, field
from http import HTTPStatus
from collections.abc import Mapping
from typing import Any, Final

import jinja2
from fastapi import Request
from openai.types.responses import (
    ResponseCodeInterpreterCallCodeDeltaEvent,
    ResponseCodeInterpreterCallCodeDoneEvent,
    ResponseCodeInterpreterCallCompletedEvent,
    ResponseCodeInterpreterCallInProgressEvent,
    ResponseCodeInterpreterCallInterpretingEvent,
    ResponseCodeInterpreterToolCallParam,
    ResponseContentPartAddedEvent,
    ResponseContentPartDoneEvent,
    ResponseFunctionCallArgumentsDeltaEvent,
    ResponseFunctionCallArgumentsDoneEvent,
    ResponseFunctionToolCall,
    ResponseFunctionWebSearch,
    ResponseOutputItem,
    ResponseOutputItemAddedEvent,
    ResponseOutputItemDoneEvent,
    ResponseOutputMessage,
    ResponseOutputText,
    ResponseReasoningItem,
    ResponseReasoningTextDeltaEvent,
    ResponseReasoningTextDoneEvent,
    ResponseStatus,
    ResponseTextDeltaEvent,
    ResponseTextDoneEvent,
    ResponseFileSearchCallInProgressEvent,
    ResponseFileSearchCallSearchingEvent,
    ResponseFileSearchCallCompletedEvent,
    ResponseWebSearchCallCompletedEvent,
    ResponseWebSearchCallInProgressEvent,
    ResponseWebSearchCallSearchingEvent,
    response_function_web_search,
    response_text_delta_event,
)

try:
    from openai.types.responses import (
        ResponseImageGenerationCallInProgressEvent,
        ResponseImageGenerationCallGeneratingEvent,
        ResponseImageGenerationCallCompletedEvent,
        ResponseImageGenerationCallPartialImageEvent,
    )
except ImportError:  # Older OpenAI python clients.
    from openai.types.responses import (  # type: ignore[no-redef]
        ResponseImageGenCallInProgressEvent as ResponseImageGenerationCallInProgressEvent,
        ResponseImageGenCallGeneratingEvent as ResponseImageGenerationCallGeneratingEvent,
        ResponseImageGenCallCompletedEvent as ResponseImageGenerationCallCompletedEvent,
        ResponseImageGenCallPartialImageEvent as ResponseImageGenerationCallPartialImageEvent,
    )
from openai.types.responses.response_output_text import Logprob, LogprobTopLogprob
from openai.types.responses.response_reasoning_item import (
    Content as ResponseReasoningTextContent,
)
from openai.types.responses.tool import Tool
from pydantic import TypeAdapter, ValidationError
from openai_harmony import Message as OpenAIHarmonyMessage

from vllm import envs
from vllm.engine.protocol import EngineClient
from vllm.entrypoints.chat_utils import (
    ChatCompletionMessageParam,
    ChatTemplateContentFormatOption,
)
from vllm.entrypoints.context import (
    ConversationContext,
    HarmonyContext,
    SimpleContext,
    StreamingHarmonyContext,
)
from vllm.entrypoints.harmony_utils import (
    construct_harmony_previous_input_messages,
    get_developer_message,
    get_stop_tokens_for_assistant_actions,
    get_system_message,
    get_user_message,
    has_custom_tools,
    parse_output_message,
    parse_remaining_state,
    parse_response_input,
    render_for_completion,
)
from vllm.entrypoints.logger import RequestLogger
from vllm.entrypoints.openai.protocol import (
    DeltaMessage,
    ErrorResponse,
    InputTokensDetails,
    OutputTokensDetails,
    RequestResponseMetadata,
    ResponseAdditionalContextEvent,
    ResponseCompletedEvent,
    ResponseCreatedEvent,
    ResponseErrorEvent,
    ResponseIncompleteEvent,
    ResponseInProgressEvent,
    ResponseQueuedEvent,
    ResponseInputOutputItem,
    ResponseRateLimitsUpdatedEvent,
    ResponseReasoningDeltaEvent,
    ResponseReasoningDoneEvent,
    ResponseReasoningSummaryAddedEvent,
    ResponseReasoningSummaryDeltaEvent,
    ResponseReasoningSummaryPart,
    ResponseReasoningSummaryPartAddedEvent,
    ResponseReasoningSummaryPartDoneEvent,
    ResponseReasoningSummaryTextDeltaEvent,
    ResponseReasoningSummaryTextDoneEvent,
    ResponseReasoningPartAddedEvent,
    ResponseReasoningPartDoneEvent,
    OpenAIErrorType,
    ResponseToolCallDeltaEvent,
    ResponseToolCallCompletedEvent,
    ResponsesRequest,
    ResponsesResponse,
    ResponsesToolOutputsRequest,
    ResponseUsage,
    StreamingResponsesResponse,
)
from vllm.entrypoints.openai.serving_engine import OpenAIServing
from vllm.entrypoints.openai.serving_models import OpenAIServingModels
from vllm.entrypoints.openai.rate_limits import RateLimitTracker, RateLimitConfig
from vllm.entrypoints.openai.reasoning_encryption import ReasoningEncryption
from vllm.entrypoints.responses_utils import (
    construct_chat_message_with_tool_call,
    convert_tool_responses_to_completions_format,
    extract_tool_types,
)
from vllm.entrypoints.tool_server import ToolServer
from vllm.inputs.data import TokensPrompt as EngineTokensPrompt
from vllm.logger import init_logger
from vllm.logprobs import Logprob as SampleLogprob
from vllm.logprobs import SampleLogprobs
from vllm.lora.request import LoRARequest
from vllm.outputs import CompletionOutput
from vllm.sampling_params import SamplingParams, StructuredOutputsParams
from vllm.transformers_utils.tokenizer import AnyTokenizer
from vllm.utils import random_uuid

logger = init_logger(__name__)


@dataclass
class PendingToolCallState:
    """Tracks state for a single pending tool call emitted in the stream."""

    item_id: str
    tool_call: ResponseFunctionToolCall
    output: list[dict[str, Any]] | None = None
    stream_started: bool = False
    stream_closed: bool = False

    def append_arguments(self, delta: str) -> None:
        if not delta:
            return
        existing = self.tool_call.arguments or ""
        self.tool_call.arguments = existing + delta

    def finalize_arguments(self, final_text: str) -> None:
        if final_text:
            self.tool_call.arguments = final_text

    @property
    def waiting_for_output(self) -> bool:
        return self.output is None


@dataclass
class ResponseStreamSession:
    """Session metadata for an in-flight streaming Responses request."""

    request: ResponsesRequest
    sampling_params: SamplingParams
    context: ConversationContext
    model_name: str
    tokenizer: AnyTokenizer
    request_metadata: RequestResponseMetadata
    lora_request: LoRARequest | None
    trace_headers: Mapping[str, str] | None
    priority: int
    current_generator: AsyncIterator[ConversationContext | None]
    pending_tool_calls: dict[str, PendingToolCallState] = field(
        default_factory=dict
    )
    tool_calls_by_item_id: dict[str, str] = field(default_factory=dict)
    resume_event: asyncio.Event = field(default_factory=asyncio.Event)
    waiting_for_tool_outputs: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def register_tool_call(
        self, item_id: str, tool_call: ResponseFunctionToolCall
    ) -> None:
        self.pending_tool_calls[tool_call.call_id] = PendingToolCallState(
            item_id=item_id,
            tool_call=tool_call,
        )
        self.tool_calls_by_item_id[item_id] = tool_call.call_id

    def append_tool_call_delta(self, item_id: str, delta: str) -> None:
        call_id = self.tool_calls_by_item_id.get(item_id)
        if call_id is None:
            return
        self.pending_tool_calls[call_id].append_arguments(delta)

    def finalize_tool_call_arguments(self, item_id: str, final_text: str) -> None:
        call_id = self.tool_calls_by_item_id.get(item_id)
        if call_id is None:
            return
        self.pending_tool_calls[call_id].finalize_arguments(final_text)

    def pop_tool_call(self, call_id: str) -> PendingToolCallState | None:
        state = self.pending_tool_calls.pop(call_id, None)
        if state is not None:
            self.tool_calls_by_item_id.pop(state.item_id, None)
        return state

    def has_pending_tool_calls(self) -> bool:
        return any(call.waiting_for_output for call in self.pending_tool_calls.values())


@dataclass
class ResponseSession:
    """Tracks lifecycle and metadata for a Responses API request."""

    id: str
    request: ResponsesRequest
    sampling_params: SamplingParams
    context: ConversationContext
    model_name: str
    tokenizer: AnyTokenizer
    request_metadata: RequestResponseMetadata
    created_time: int
    event_deque: deque[StreamingResponsesResponse]
    new_event_signal: asyncio.Event
    generator: AsyncIterator[ConversationContext | None]
    stream_state: ResponseStreamSession | None = None
    background_task: asyncio.Task | None = None
    status: ResponseStatus | str = "in_progress"
    completed: bool = False
    last_activity_time: float = field(default_factory=time.monotonic)
    user_id: str = "anonymous"
    event_queue_bytes: int = 0

    def touch(self) -> None:
        self.last_activity_time = time.monotonic()

    def mark_completed(self) -> None:
        self.completed = True
        self.touch()


class ResponseSessionManager:
    """Thread-safe registry for active Responses API sessions."""

    def __init__(
        self,
        session_ttl: float = 600.0,
        max_sessions: int = 1000,
    ) -> None:
        self._sessions: dict[str, ResponseSession] = {}
        self._lock = threading.RLock()
        self._session_ttl = max(session_ttl, 0.0)
        self._max_sessions = max(max_sessions, 1)

    def add_session(self, session: ResponseSession) -> None:
        with self._lock:
            self._cleanup_locked()
            self._sessions[session.id] = session
            self._evict_excess_locked()

    def get_session(self, session_id: str) -> ResponseSession | None:
        with self._lock:
            self._cleanup_locked()
            session = self._sessions.get(session_id)
            if session is not None:
                session.touch()
            return session

    def remove_session(self, session_id: str) -> ResponseSession | None:
        with self._lock:
            removed = self._sessions.pop(session_id, None)
            return removed

    def list_active_sessions(self) -> list[ResponseSession]:
        with self._lock:
            return list(self._sessions.values())

    def cleanup_expired_sessions(self) -> None:
        with self._lock:
            self._cleanup_locked()

    def _cleanup_locked(self) -> None:
        if self._session_ttl <= 0:
            return
        now = time.monotonic()
        expired: list[str] = []
        for session_id, session in self._sessions.items():
            if (
                session.completed
                and (now - session.last_activity_time) >= self._session_ttl
            ):
                expired.append(session_id)
        for session_id in expired:
            self._sessions.pop(session_id, None)

    def _evict_excess_locked(self) -> None:
        if len(self._sessions) <= self._max_sessions:
            return
        sorted_sessions = sorted(
            self._sessions.values(),
            key=lambda s: s.last_activity_time,
        )
        while len(self._sessions) > self._max_sessions and sorted_sessions:
            victim = sorted_sessions.pop(0)
            logger.warning(
                "Evicting session %s due to max session limit (%d)",
                victim.id,
                self._max_sessions,
            )
            victim_task = victim.background_task
            if victim_task is not None:
                victim_task.cancel()
            self._sessions.pop(victim.id, None)


class ReasoningSummaryExtractor:
    """Utility class to build concise reasoning summaries for SSE events."""

    def __init__(self, max_summary_length: int = 480, chunk_size: int = 160) -> None:
        self.max_summary_length = max_summary_length
        self.chunk_size = chunk_size

    def extract_summary(self, reasoning_text: str) -> str:
        """Return a concise summary using simple sentence heuristics."""

        text = reasoning_text.strip()
        if not text:
            return ""
        sentences = re.split(r"(?<=[.!?])\s+", text)
        summary = " ".join(sentences[:2]).strip()
        if not summary:
            summary = text
        if len(summary) > self.max_summary_length:
            summary = summary[: self.max_summary_length].rstrip()
        return summary

    def iter_summary_chunks(self, summary_text: str) -> list[str]:
        """Split summary into smaller chunks for streaming."""

        if not summary_text:
            return []
        return [
            summary_text[i : i + self.chunk_size]
            for i in range(0, len(summary_text), self.chunk_size)
        ]


TOOL_VALIDATOR = TypeAdapter(Tool)


class OpenAIServingResponses(OpenAIServing):
    _COMPAT_INCLUDE_ALLOWLIST: Final[frozenset[str]] = frozenset(
        {
            "code_interpreter_call.outputs",
            "computer_call_output.output.image_url",
            "file_search_call.results",
            "message.input_image.image_url",
            "message.output_text.logprobs",
            "reasoning.encrypted_content",
            "web_search_call.action.sources",
        }
    )
    _COMPAT_FORBIDDEN_FIELDS: Final[tuple[str, ...]] = (
        "request_id",
        "mm_processor_kwargs",
        "priority",
        "cache_salt",
        "enable_response_messages",
        "previous_input_messages",
    )

    def __init__(
        self,
        engine_client: EngineClient,
        models: OpenAIServingModels,
        *,
        request_logger: RequestLogger | None,
        chat_template: str | None,
        chat_template_content_format: ChatTemplateContentFormatOption,
        return_tokens_as_token_ids: bool = False,
        reasoning_parser: str = "",
        enable_auto_tools: bool = False,
        tool_parser: str | None = None,
        tool_server: ToolServer | None = None,
        enable_prompt_tokens_details: bool = False,
        enable_force_include_usage: bool = False,
        enable_log_outputs: bool = False,
        log_error_stack: bool = False,
        legacy_reasoning_events: bool = False,
        reasoning_encryption_key: str | None = None,
        enable_rate_limit_events: bool = False,
        rate_limit_requests_per_minute: int = 60,
        rate_limit_requests_per_hour: int = 1000,
        rate_limit_tokens_per_minute: int = 100_000,
        tool_outputs_timeout: float = 300.0,
        responses_session_ttl: float = 600.0,
        rate_limits_config: dict[str, Any] | None = None,
        enable_computer_call: bool = False,
        image_service_config: Mapping[str, Any] | None = None,
        disable_responses_store: bool = False,
        responses_store_ttl: float = 3600.0,
        responses_store_max_entries: int = 1000,
        responses_store_max_bytes: int | None = None,
        default_openai_organization: str | None = None,
        default_openai_version: str | None = None,
        max_request_body_tokens: int | None = None,
        max_request_body_bytes: int | None = None,
        max_tool_output_bytes: int | None = None,
        responses_max_active_sessions: int = 1000,
        max_stream_event_bytes: int | None = None,
        responses_stream_buffer_max_bytes: int | None = None,
        compatibility_mode: bool = False,
        ping_interval_seconds: float = 15.0,
        default_service_tier: str = "auto",
        allowed_service_tiers: Sequence[str] | None = None,
    ) -> None:
        super().__init__(
            engine_client=engine_client,
            models=models,
            request_logger=request_logger,
            return_tokens_as_token_ids=return_tokens_as_token_ids,
            log_error_stack=log_error_stack,
        )

        self.chat_template = chat_template
        self.chat_template_content_format: Final = chat_template_content_format
        self.enable_log_outputs = enable_log_outputs
        self.compatibility_mode = compatibility_mode
        self.legacy_reasoning_events = (
            False if compatibility_mode else legacy_reasoning_events
        )
        self.reasoning_summary_extractor = ReasoningSummaryExtractor()
        self.reasoning_encryption = ReasoningEncryption(reasoning_encryption_key)
        self.default_openai_organization = default_openai_organization
        self.default_openai_version = default_openai_version
        self.max_request_body_tokens = max_request_body_tokens
        self.max_request_body_bytes = max_request_body_bytes
        self.max_tool_output_bytes = max_tool_output_bytes
        self.max_stream_event_bytes = (
            None
            if max_stream_event_bytes in (None, 0)
            else max(1, int(max_stream_event_bytes))
        )
        self.responses_stream_buffer_max_bytes = (
            None
            if responses_stream_buffer_max_bytes in (None, 0)
            else max(1, int(responses_stream_buffer_max_bytes))
        )
        self.ping_interval_seconds = max(0.0, float(ping_interval_seconds))
        allowed = allowed_service_tiers or [
            "auto",
            "default",
            "flex",
            "scale",
            "priority",
        ]
        self.allowed_service_tiers: set[str] = {
            tier.strip().lower() for tier in allowed
        }
        if "auto" not in self.allowed_service_tiers:
            self.allowed_service_tiers.add("auto")
        normalized_default = default_service_tier.lower()
        if normalized_default not in self.allowed_service_tiers:
            logger.warning(
                "Default service tier %s is not allowed; falling back to 'auto'.",
                default_service_tier,
            )
            normalized_default = "auto"
        self.default_service_tier = normalized_default
        self.rate_limit_config = RateLimitConfig.from_dict(rate_limits_config)
        tracker_needed = enable_rate_limit_events or self.rate_limit_config.enabled
        tracker_reqs_per_minute = (
            self.rate_limit_config.requests_per_minute
            if self.rate_limit_config.enabled
            else rate_limit_requests_per_minute
        )
        tracker_reqs_per_hour = (
            self.rate_limit_config.requests_per_hour
            if self.rate_limit_config.enabled
            else rate_limit_requests_per_hour
        )
        tracker_tokens_per_minute = (
            self.rate_limit_config.tokens_per_minute
            if self.rate_limit_config.enabled
            else rate_limit_tokens_per_minute
        )
        request_limits_enabled = (
            self.rate_limit_config.request_limits_enabled
            if self.rate_limit_config.enabled
            else True
        )
        token_limits_enabled = (
            self.rate_limit_config.token_limits_enabled
            if self.rate_limit_config.enabled
            else True
        )
        self.rate_limiter: RateLimitTracker | None = None
        if tracker_needed:
            self.rate_limiter = RateLimitTracker(
                requests_per_minute=tracker_reqs_per_minute,
                requests_per_hour=tracker_reqs_per_hour,
                tokens_per_minute=tracker_tokens_per_minute,
                enable_request_limits=request_limits_enabled,
                enable_token_limits=token_limits_enabled,
            )
        self.enforce_rate_limits = bool(
            self.rate_limit_config.enabled and self.rate_limit_config.enforce
        )
        self.rate_limit_events_enabled = enable_rate_limit_events
        self.tool_outputs_timeout = float(tool_outputs_timeout)

        self.reasoning_parser = self._get_reasoning_parser(
            reasoning_parser_name=reasoning_parser
        )
        self.enable_prompt_tokens_details = enable_prompt_tokens_details
        self.enable_force_include_usage = enable_force_include_usage
        self.enable_computer_call = enable_computer_call
        self.image_service_config = self._normalize_image_service_config(
            image_service_config
        )
        self._image_tool_error_message = (
            "Image generation tools are disabled. Start vLLM with a multimodal "
            "model or pass --image-service-config pointing to an external image API."
        )
        if self.image_service_config:
            provider = self.image_service_config.get("provider", "external image API")
            logger.info("External image service configured: %s", provider)
        self.default_sampling_params = self.model_config.get_diff_sampling_param()
        if self.default_sampling_params:
            source = self.model_config.generation_config
            source = "model" if source == "auto" else source
            logger.info(
                "Using default chat sampling params from %s: %s",
                source,
                self.default_sampling_params,
            )

        # Manage persisted Responses for GET /v1/responses.
        self.enable_store = not disable_responses_store
        if envs.VLLM_ENABLE_RESPONSES_API_STORE:
            self.enable_store = True
        self.response_store_ttl = max(float(responses_store_ttl), 0.0)
        self.response_store_max_entries = max(int(responses_store_max_entries), 1)
        self.response_store_max_bytes = (
            int(responses_store_max_bytes)
            if responses_store_max_bytes is not None
            else None
        )
        self.response_store: dict[str, ResponsesResponse] = {}
        self.response_store_expirations: dict[str, float] = {}
        self.response_store_sizes: dict[str, int] = {}
        self.response_store_total_bytes = 0
        self.response_store_lock = asyncio.Lock()
        self.response_input_items: dict[str, list[dict[str, Any]]] = {}
        if not self.enable_store:
            logger.warning_once(
                "Responses store disabled. GET /v1/responses will always return 404."
            )
        elif self.response_store_ttl == 0:
            logger.warning_once(
                "responses_store_ttl=0 disables eviction; stored responses "
                "will accumulate until restart."
            )

        self.use_harmony = self.model_config.hf_config.model_type == "gpt_oss"
        if self.use_harmony:
            logger.warning(
                "For gpt-oss, we ignore --enable-auto-tool-choice "
                "and always enable tool use."
            )
            # OpenAI models have two EOS-like tokens: <|return|> and <|call|>.
            # We need to add them to the stop token ids.
            if "stop_token_ids" not in self.default_sampling_params:
                self.default_sampling_params["stop_token_ids"] = []
            self.default_sampling_params["stop_token_ids"].extend(
                get_stop_tokens_for_assistant_actions()
            )
        self.enable_auto_tools = enable_auto_tools
        # set up tool use
        self.tool_parser = self._get_tool_parser(
            tool_parser_name=tool_parser, enable_auto_tools=enable_auto_tools
        )
        self.exclude_tools_when_tool_choice_none = False
        # Store original input messages for background/previous_response flows.
        self.msg_store: dict[str, list[ChatCompletionMessageParam]] = {}

        self.background_tasks: dict[str, asyncio.Task] = {}
        self.session_manager = ResponseSessionManager(
            session_ttl=responses_session_ttl,
            max_sessions=responses_max_active_sessions,
        )

        self.tool_server = tool_server

    def _build_reasoning_delta_events(
        self,
        *,
        response_id: str,
        delta_text: str,
        item_id: str,
        output_index: int,
        content_index: int,
    ) -> list[StreamingResponsesResponse]:
        """Return legacy and/or OpenAI-compatible reasoning delta events."""

        events: list[StreamingResponsesResponse] = []
        if self.legacy_reasoning_events or self.compatibility_mode:
            events.append(
                ResponseReasoningTextDeltaEvent(
                    type="response.reasoning_text.delta",
                    sequence_number=-1,
                    content_index=content_index,
                    output_index=output_index,
                    item_id=item_id,
                    delta=delta_text,
                )
            )
        if not self.legacy_reasoning_events:
            events.append(
                ResponseReasoningDeltaEvent(
                    type="response.reasoning.delta",
                    response={"id": response_id},
                    delta=delta_text,
                    sequence_number=-1,
                )
            )
        return events

    def _build_reasoning_done_events(
        self,
        *,
        response_id: str,
        reasoning_text: str,
        item_id: str,
        output_index: int,
        content_index: int,
    ) -> list[StreamingResponsesResponse]:
        """Return legacy and/or OpenAI-compatible reasoning done events."""

        events: list[StreamingResponsesResponse] = []
        if self.legacy_reasoning_events or self.compatibility_mode:
            events.append(
                ResponseReasoningTextDoneEvent(
                    type="response.reasoning_text.done",
                    item_id=item_id,
                    sequence_number=-1,
                    output_index=output_index,
                    content_index=content_index,
                    text=reasoning_text,
                )
            )
        if not self.legacy_reasoning_events:
            events.append(
                ResponseReasoningDoneEvent(
                    type="response.reasoning.done",
                    response={"id": response_id},
                    reasoning={"content": reasoning_text},
                    sequence_number=-1,
                )
            )
        return events

    def _build_tool_call_delta_event(
        self,
        *,
        response_id: str,
        tool_call_id: str,
        tool_name: str | None,
        arguments_text: str,
        status: str = "in_progress",
    ) -> ResponseToolCallDeltaEvent:
        """Create an OpenAI-compatible response.tool_call.delta event."""
        if logger.isEnabledFor(logging.DEBUG):
            try:
                logger.debug(
                    "TOOL_CALL delta: response=%s call_id=%s name=%s args_len=%d",
                    response_id,
                    tool_call_id,
                    tool_name,
                    len(arguments_text or ""),
                )
            except Exception:
                pass
        chunk = self._serialize_tool_call_chunk(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            arguments_text=arguments_text,
            status=status,
        )
        return ResponseToolCallDeltaEvent(
            type="response.tool_call.delta",
            response={"id": response_id},
            delta=chunk,
            sequence_number=-1,
        )

    @staticmethod
    def _serialize_tool_call_chunk(
        *,
        tool_call_id: str,
        tool_name: str | None,
        arguments_text: str,
        status: str,
    ) -> str:
        payload = [
            {
                "type": "tool_call",
                "id": tool_call_id,
                "call_id": tool_call_id,
                "name": tool_name,
                "arguments": arguments_text,
                "status": status,
            }
        ]
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _normalize_image_service_config(
        config: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        if config is None:
            return {}
        if not isinstance(config, Mapping):
            raise ValueError("image_service_config must be a mapping.")
        normalized = dict(config)
        required_fields = ("provider", "api_base", "api_key_env", "default_model")
        missing = [field for field in required_fields if not normalized.get(field)]
        if missing:
            missing_fields = ", ".join(sorted(missing))
            raise ValueError(
                "image_service_config is missing required field(s): "
                f"{missing_fields}. See ImageServices_HOWTO.md for the template."
            )
        return normalized

    def _generate_reasoning_summary_events(
        self,
        *,
        response_id: str,
        reasoning_text: str,
        item_id: str | None,
        output_index: int | None,
    ) -> list[StreamingResponsesResponse]:
        """Create reasoning summary events for streaming."""

        summary = self.reasoning_summary_extractor.extract_summary(reasoning_text)
        if not summary:
            return []

        events: list[StreamingResponsesResponse] = [
            ResponseReasoningSummaryAddedEvent(
                type="response.reasoning.summary.added",
                response={"id": response_id},
                sequence_number=-1,
            )
        ]
        summary_chunks = list(
            self.reasoning_summary_extractor.iter_summary_chunks(summary)
        )
        for summary_index, chunk in enumerate(summary_chunks):
            events.append(
                ResponseReasoningSummaryDeltaEvent(
                    type="response.reasoning.summary.delta",
                    response={"id": response_id},
                    delta=chunk,
                    sequence_number=-1,
                )
            )
            if item_id is not None and output_index is not None:
                events.append(
                    ResponseReasoningSummaryPartAddedEvent(
                        type="response.reasoning_summary_part.added",
                        item_id=item_id,
                        output_index=output_index,
                        summary_index=summary_index,
                        part=ResponseReasoningSummaryPart(
                            type="summary_text",
                            text="",
                        ),
                        sequence_number=-1,
                    )
                )
                events.append(
                    ResponseReasoningSummaryTextDeltaEvent(
                        type="response.reasoning_summary_text.delta",
                        item_id=item_id,
                        output_index=output_index,
                        summary_index=summary_index,
                        delta=chunk,
                        sequence_number=-1,
                    )
                )
                events.append(
                    ResponseReasoningSummaryTextDoneEvent(
                        type="response.reasoning_summary_text.done",
                        item_id=item_id,
                        output_index=output_index,
                        summary_index=summary_index,
                        text=chunk,
                        sequence_number=-1,
                    )
                )
                events.append(
                    ResponseReasoningSummaryPartDoneEvent(
                        type="response.reasoning_summary_part.done",
                        item_id=item_id,
                        output_index=output_index,
                        summary_index=summary_index,
                        part=ResponseReasoningSummaryPart(
                            type="summary_text",
                            text=chunk,
                        ),
                        sequence_number=-1,
                    )
                )
        return events

    def _should_emit_encrypted_reasoning(
        self,
        request: ResponsesRequest,
    ) -> bool:
        include = request.include
        if include is None:
            return False
        return "reasoning.encrypted_content" in include

    def _should_emit_computer_call_placeholder(
        self,
        request: ResponsesRequest,
    ) -> bool:
        return self.enable_computer_call and self._request_includes(
            request, "computer_call_output.output.image_url"
        )

    def _image_tools_available(self) -> bool:
        return self.model_config.is_multimodal_model or bool(
            self.image_service_config
        )

    def _require_image_tools_enabled(self, tool_name: str | None = None) -> None:
        if self._image_tools_available():
            return
        if tool_name:
            logger.warning(
                "Image tool call %s rejected because no multimodal model or "
                "image_service_config is available.",
                tool_name,
            )
        raise RuntimeError(self._image_tool_error_message)

    def _build_context_event(
        self,
        *,
        response_id: str,
        payload: dict[str, Any],
    ) -> ResponseAdditionalContextEvent:
        return ResponseAdditionalContextEvent(
            type="response.additional_context",
            response={"id": response_id},
            context=payload,
            sequence_number=-1,
        )

    def _build_file_search_results_event(
        self,
        request: ResponsesRequest,
        *,
        response_id: str,
        item_id: str,
        function_name: str,
        parsed_args: dict[str, Any],
    ) -> ResponseAdditionalContextEvent | None:
        if not self._request_includes(request, "file_search_call.results"):
            return None
        payload = {
            "file_search_call.results": [
                {
                    "id": item_id,
                    "type": function_name,
                    "query": parsed_args.get("query")
                    or parsed_args.get("pattern")
                    or "",
                    "url": parsed_args.get("url") or parsed_args.get("cursor") or "",
                }
            ]
        }
        return self._build_context_event(
            response_id=response_id,
            payload=payload,
        )

    def _build_web_search_sources_event(
        self,
        request: ResponsesRequest,
        *,
        response_id: str,
        item_id: str,
        function_name: str,
        parsed_args: dict[str, Any],
    ) -> ResponseAdditionalContextEvent | None:
        if not self._request_includes(
            request, "web_search_call.action.sources"
        ):
            return None
        raw_sources = parsed_args.get("sources")
        if raw_sources is None:
            raw_sources = []
        payload = {
            "web_search_call.action.sources": [
                {
                    "id": item_id,
                    "type": function_name,
                    "query": parsed_args.get("query") or "",
                    "sources": raw_sources,
                }
            ]
        }
        return self._build_context_event(
            response_id=response_id,
            payload=payload,
        )

    def _build_file_search_call_events(
        self,
        *,
        item_id: str,
        output_index: int,
    ) -> list[StreamingResponsesResponse]:
        return [
            ResponseFileSearchCallInProgressEvent(
                type="response.file_search_call.in_progress",
                item_id=item_id,
                output_index=output_index,
                sequence_number=-1,
            ),
            ResponseFileSearchCallSearchingEvent(
                type="response.file_search_call.searching",
                item_id=item_id,
                output_index=output_index,
                sequence_number=-1,
            ),
            ResponseFileSearchCallCompletedEvent(
                type="response.file_search_call.completed",
                item_id=item_id,
                output_index=output_index,
                sequence_number=-1,
            ),
        ]

    def _build_image_generation_call_events(
        self,
        *,
        item_id: str,
        output_index: int,
        partial_image_b64: str | None = None,
    ) -> list[StreamingResponsesResponse]:
        events: list[StreamingResponsesResponse] = [
            ResponseImageGenerationCallInProgressEvent(
                type="response.image_generation_call.in_progress",
                item_id=item_id,
                output_index=output_index,
                sequence_number=-1,
            ),
            ResponseImageGenerationCallGeneratingEvent(
                type="response.image_generation_call.generating",
                item_id=item_id,
                output_index=output_index,
                sequence_number=-1,
            ),
        ]
        if partial_image_b64 is not None:
            events.append(
                ResponseImageGenerationCallPartialImageEvent(
                    type="response.image_generation_call.partial_image",
                    item_id=item_id,
                    output_index=output_index,
                    partial_image_index=0,
                    partial_image_b64=partial_image_b64,
                    sequence_number=-1,
                )
            )
        events.append(
            ResponseImageGenerationCallCompletedEvent(
                type="response.image_generation_call.completed",
                item_id=item_id,
                output_index=output_index,
                sequence_number=-1,
            )
        )
        return events

    def _build_message_input_image_event(
        self,
        request: ResponsesRequest,
    ) -> ResponseAdditionalContextEvent | None:
        if not self._request_includes(
            request, "message.input_image.image_url"
        ):
            return None
        request_input = request.input
        if not isinstance(request_input, list):
            return None
        entries: list[dict[str, Any]] = []
        for idx, item in enumerate(request_input):
            payload = self._serialize_input_item(item)
            contents = payload.get("content")
            if not isinstance(contents, list):
                continue
            urls = [
                part.get("image_url")
                for part in contents
                if isinstance(part, dict)
                and part.get("type") in {"input_image", "image_url"}
                and part.get("image_url")
            ]
            if urls:
                entries.append(
                    {
                        "id": payload.get("id")
                        or f"item_{idx}_{random_uuid()}",
                        "role": payload.get("role", "user"),
                        "image_urls": urls,
                    }
                )
        if not entries:
            return None
        return self._build_context_event(
            response_id=request.request_id,
            payload={"message.input_image.image_url": entries},
        )

    def _generate_additional_context_events(
        self,
        request: ResponsesRequest,
        *,
        response_id: str,
        reasoning_text: str,
    ) -> list[StreamingResponsesResponse]:
        if not self._should_emit_encrypted_reasoning(request):
            return []
        if not reasoning_text.strip():
            return []

        encrypted_payload = self.reasoning_encryption.encrypt_reasoning(
            reasoning_text
        )
        logger.debug(
            "Emitting response.additional_context for %s (%d bytes)",
            response_id,
            len(encrypted_payload),
        )
        return [
            self._build_context_event(
                response_id=response_id,
                payload={"reasoning.encrypted_content": encrypted_payload},
            )
        ]

    def _validate_generator_input(
        self, engine_prompt: EngineTokensPrompt
    ) -> ErrorResponse | None:
        """Add validations to the input to the generator here."""
        if self.max_model_len <= len(engine_prompt["prompt_token_ids"]):
            error_message = (
                "The engine prompt length"
                f" {len(engine_prompt['prompt_token_ids'])} "
                f"exceeds the max_model_len {self.max_model_len}. "
                "Please reduce prompt."
            )
            return self.create_error_response(
                err_type="invalid_request_error",
                message=error_message,
                status_code=HTTPStatus.BAD_REQUEST,
            )
        return None

    def _apply_prompt_cache_key(self, request: ResponsesRequest) -> None:
        """Map OpenAI's prompt_cache_key to the internal cache salt."""

        cache_key = getattr(request, "prompt_cache_key", None)
        if not cache_key:
            return
        if request.cache_salt and request.cache_salt != cache_key:
            logger.warning_once(
                "Both cache_salt (%s) and prompt_cache_key (%s) provided; "
                "using cache_salt.",
                request.cache_salt,
                cache_key,
            )
            return
        request.cache_salt = cache_key

    async def _maybe_reserve_rate_limit(
        self,
        user_id: str,
        sampling_params: SamplingParams,
    ) -> ErrorResponse | None:
        if self.rate_limiter is None:
            return None
        if self.enforce_rate_limits:
            token_reservation = (
                sampling_params.max_tokens
                if self.rate_limit_config.token_limits_enabled
                else 0
            )
            allowed, retry_after = await self.rate_limiter.check_and_reserve(
                user_id,
                tokens=token_reservation or 0,
            )
            if not allowed:
                return self.create_error_response(
                    message="Rate limit exceeded. Please retry later.",
                    err_type=OpenAIErrorType.RATE_LIMIT_ERROR,
                    status_code=HTTPStatus.TOO_MANY_REQUESTS,
                    retry_after=retry_after,
                )
        elif self.rate_limit_events_enabled:
            await self.rate_limiter.record_request(user_id)
        return None

    def _validate_request_size(
        self,
        request: ResponsesRequest,
        *,
        serialized_body_bytes: int | None = None,
        prompt_token_count: int | None = None,
    ) -> ErrorResponse | None:
        if (
            self.max_request_body_bytes is not None
            and serialized_body_bytes is not None
            and serialized_body_bytes > self.max_request_body_bytes
        ):
            return self.create_error_response(
                err_type="invalid_request_error",
                message=(
                    f"Request body exceeds limit "
                    f"{self.max_request_body_bytes} bytes."
                ),
                status_code=HTTPStatus.BAD_REQUEST,
            )
        if (
            self.max_request_body_tokens is not None
            and prompt_token_count is not None
            and prompt_token_count > self.max_request_body_tokens
        ):
            return self.create_error_response(
                err_type="invalid_request_error",
                message=(
                    f"Prompt tokens ({prompt_token_count}) exceed limit "
                    f"{self.max_request_body_tokens}."
                ),
                status_code=HTTPStatus.BAD_REQUEST,
            )
        return None

    def _request_includes(
        self, request: ResponsesRequest, include_name: str
    ) -> bool:
        include = request.include
        if include is None:
            return False
        return isinstance(include, list) and include_name in include

    async def build_rate_limit_headers(self, user_id: str) -> dict[str, str]:
        if self.rate_limiter is None:
            return {}
        stats = await self.rate_limiter.build_header_stats(user_id)
        headers: dict[str, str] = {}
        req_stats = stats.get("requests_1min")
        if req_stats:
            headers["x-ratelimit-limit-requests"] = str(req_stats["limit"])
            headers["x-ratelimit-remaining-requests"] = str(req_stats["remaining"])
        token_stats = stats.get("tokens_1min")
        if token_stats and self.rate_limit_config.token_limits_enabled:
            headers["x-ratelimit-limit-tokens"] = str(token_stats["limit"])
            headers["x-ratelimit-remaining-tokens"] = str(token_stats["remaining"])
        return headers

    def get_session_user(self, response_id: str) -> str | None:
        session = self.session_manager.get_session(response_id)
        if session is not None:
            return session.user_id
        return None

    def _validate_include_options(
        self, request: ResponsesRequest
    ) -> ErrorResponse | None:
        include = request.include
        if not include:
            return None

        if (
            "computer_call_output.output.image_url" in include
            and not self.enable_computer_call
        ):
            return self.create_error_response(
                err_type="invalid_request_error",
                message=(
                    "computer_call_output.output.image_url requires "
                    "--enable-computer-call and a multimodal model."
                ),
                status_code=HTTPStatus.BAD_REQUEST,
            )
        return None

    @staticmethod
    def _safe_json_loads(
        payload: str,
        *,
        tool_name: str,
    ) -> dict[str, Any] | None:
        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            logger.warning(
                "Invalid JSON arguments for tool %s: %s",
                tool_name,
                exc,
            )
            return None

    def _validate_create_responses_input(
        self, request: ResponsesRequest
    ) -> ErrorResponse | None:
        service_tier_error = self._validate_service_tier(request)
        if service_tier_error is not None:
            return service_tier_error
        compat_error = self._validate_compatibility_request(request)
        if compat_error is not None:
            return compat_error
        if self.use_harmony and request.is_include_output_logprobs():
            return self.create_error_response(
                err_type="invalid_request_error",
                message="logprobs are not supported with gpt-oss models",
                status_code=HTTPStatus.BAD_REQUEST,
            )
        if request.previous_input_messages and request.previous_response_id:
            return self.create_error_response(
                err_type="invalid_request_error",
                message="Only one of `previous_input_messages` and "
                "`previous_response_id` can be set.",
                status_code=HTTPStatus.BAD_REQUEST,
            )
        include_error = self._validate_include_options(request)
        if include_error is not None:
            return include_error
        serialized_size = len(request.model_dump_json().encode("utf-8"))
        size_error = self._validate_request_size(
            request,
            serialized_body_bytes=serialized_size,
        )
        if size_error is not None:
            return size_error
        if request.store and not self.enable_store:
            return self._make_store_not_supported_error()
        if request.background and not request.store:
            return self.create_error_response(
                err_type="invalid_request_error",
                message="background requests require `store=true`.",
                status_code=HTTPStatus.BAD_REQUEST,
            )
        if request.background and not self.enable_store:
            return self._make_store_not_supported_error()
        return None

    def _validate_compatibility_request(
        self, request: ResponsesRequest
    ) -> ErrorResponse | None:
        if not self.compatibility_mode:
            return None
        fields_set = getattr(request, "model_fields_set", set())
        forbidden = sorted(
            field for field in self._COMPAT_FORBIDDEN_FIELDS if field in fields_set
        )
        if forbidden:
            return self.create_error_response(
                err_type="invalid_request_error",
                message=(
                    "The following fields are not supported in compatibility mode: "
                    + ", ".join(forbidden)
                ),
                status_code=HTTPStatus.BAD_REQUEST,
            )
        include = request.include or []
        if include:
            invalid = [
                item
                for item in include
                if item not in self._COMPAT_INCLUDE_ALLOWLIST
            ]
            if invalid:
                logger.info(
                    "Compatibility mode: allowing unsupported include targets: %s",
                    ", ".join(invalid),
                )
        return None

    def _validate_service_tier(
        self, request: ResponsesRequest
    ) -> ErrorResponse | None:
        tier = (request.service_tier or "auto").lower()
        if tier == "auto":
            tier = self.default_service_tier
        if tier not in self.allowed_service_tiers:
            return self.create_error_response(
                err_type="invalid_request_error",
                message=(
                    f"service_tier '{request.service_tier}' is not allowed on "
                    "this server."
                ),
                status_code=HTTPStatus.BAD_REQUEST,
            )
        request.service_tier = tier
        return None

    async def create_responses(
        self,
        request: ResponsesRequest,
        raw_request: Request | None = None,
    ) -> (
        AsyncGenerator[StreamingResponsesResponse, None]
        | ResponsesResponse
        | ErrorResponse
    ):
        error_check_ret = await self._check_model(request)
        if error_check_ret is not None:
            logger.error("Error with model %s", error_check_ret)
            return error_check_ret
        maybe_validation_error = self._validate_create_responses_input(request)
        if maybe_validation_error is not None:
            return maybe_validation_error

        # If the engine is dead, raise the engine's DEAD_ERROR.
        # This is required for the streaming case, where we return a
        # success status before we actually start generating text :).
        if self.engine_client.errored:
            raise self.engine_client.dead_error

        self._apply_prompt_cache_key(request)
        try:
            self._normalize_request_tools(request)
        except ValueError as exc:
            return self.create_error_response(str(exc))
        user_id = request.user or "anonymous"

        # Handle the previous response ID.
        prev_response_id = request.previous_response_id
        if prev_response_id is not None:
            prev_response = await self._get_stored_response(prev_response_id)
            if prev_response is None:
                return self._make_not_found_error(prev_response_id)
        else:
            prev_response = None

        # If a streaming session is waiting for tool outputs and the client
        # posts a new /v1/responses with function_call items (Codex behavior),
        # treat this as a continuation: feed the pending tool call(s) and
        # resume the original stream instead of starting a new turn.
        if (
            prev_response is not None
            and isinstance(request.input, list)
        ):
            response_session = self.session_manager.get_session(prev_response.id)
            if response_session is not None and response_session.stream_state is not None:
                stream_state = response_session.stream_state
                # Only handle if the original stream is actually waiting.
                if stream_state.waiting_for_tool_outputs or stream_state.has_pending_tool_calls():
                    acknowledged_any = False
                    async with stream_state.lock:
                        for input_item in request.input:
                            if isinstance(input_item, ResponseFunctionToolCall):
                                call_id = input_item.call_id
                                if not call_id:
                                    continue
                                pending_call = stream_state.pending_tool_calls.get(call_id)
                                if pending_call is None:
                                    continue
                                # Accept completion regardless of outputs; client may not
                                # provide explicit output payload. Convert an empty output.
                                payload = ResponsesToolOutputsRequest(
                                    tool_call_id=call_id,
                                    output=[],
                                )
                                harmony_message = self._convert_tool_outputs_to_message(
                                    pending_call, payload
                                )
                                stream_state.context.append_tool_output([harmony_message])

                                # In compatibility mode, also update msg_store so new generation sees tool outputs
                                if self.compatibility_mode and prev_response.id in self.msg_store:
                                    self.msg_store[prev_response.id].append(harmony_message)
                                    logger.debug(
                                        "Response %s (compatibility mode): updated msg_store with tool output for call_id=%s",
                                        prev_response.id,
                                        call_id
                                    )

                                pending_call.output = []
                                stream_state.pop_tool_call(call_id)
                                acknowledged_any = True
                        if acknowledged_any and not stream_state.has_pending_tool_calls():
                            self._resume_session_after_tool_call(stream_state)
                    if acknowledged_any:
                        # In standard mode: let original streaming connection continue
                        # In compatibility mode: original stream is closed, start NEW generation
                        if not self.compatibility_mode:
                            logger.debug(
                                "Response %s: resuming original stream with tool outputs",
                                prev_response.id
                            )
                            return {"id": prev_response.id, "status": "in_progress"}
                        else:
                            logger.debug(
                                "Response %s (compatibility mode): original stream closed, "
                                "continuing with NEW generation containing tool outputs",
                                prev_response.id
                            )
                            # Fall through to start new generation with context from previous

        try:
            lora_request = self._maybe_get_adapters(request)
            model_name = self.models.model_name(lora_request)
            tokenizer = await self.engine_client.get_tokenizer()

            if self.use_harmony:
                messages, request_prompts, engine_prompts = (
                    self._make_request_with_harmony(request, prev_response)
                )
            else:
                messages, request_prompts, engine_prompts = await self._make_request(
                    request, prev_response, tokenizer
                )

        except (
            ValueError,
            TypeError,
            RuntimeError,
            jinja2.TemplateError,
            NotImplementedError,
        ) as e:
            logger.exception("Error in preprocessing prompt inputs")
            return self.create_error_response(f"{e} {e.__cause__}")

        header_request_id = None
        if raw_request is not None:
            header_request_id = raw_request.headers.get("X-Request-Id")
        mismatch_error = self._maybe_check_request_id(header_request_id, request)
        if mismatch_error is not None:
            return mismatch_error

        request_metadata = RequestResponseMetadata(
            request_id=request.request_id,
            request_header_id=header_request_id,
        )
        if raw_request:
            raw_request.state.request_metadata = request_metadata

        # Schedule the request and get the result generator.
        generators: list[AsyncGenerator[ConversationContext, None]] = []
        request_trace_headers: Mapping[str, str] | None = None

        builtin_tool_list: list[str] = []
        if self.use_harmony and self.tool_server is not None:
            if self.tool_server.has_tool("browser"):
                builtin_tool_list.append("browser")
            if self.tool_server.has_tool("python"):
                builtin_tool_list.append("python")
            if self.tool_server.has_tool("container"):
                builtin_tool_list.append("container")

        if self.tool_server is not None:
            available_tools = builtin_tool_list
        else:
            assert len(builtin_tool_list) == 0
            available_tools = []
        try:
            for i, engine_prompt in enumerate(engine_prompts):
                maybe_error = self._validate_generator_input(engine_prompt)
                if maybe_error is not None:
                    return maybe_error

                default_max_tokens = self.max_model_len - len(
                    engine_prompt["prompt_token_ids"]
                )

                sampling_params = request.to_sampling_params(
                    default_max_tokens, self.default_sampling_params
                )

                # Log sampling parameters for debugging
                seed_info = "None"
                if sampling_params.seed is not None:
                    if request.seed is None and request.randomize:
                        seed_info = f"{sampling_params.seed} (auto-generated)"
                    else:
                        seed_info = str(sampling_params.seed)

                logger.debug(
                    "Request %s sampling params: temperature=%.2f, top_p=%.2f, "
                    "top_k=%d, min_p=%.3f, repetition_penalty=%.2f, "
                    "presence_penalty=%.2f, frequency_penalty=%.2f, seed=%s, max_tokens=%d",
                    request.request_id,
                    sampling_params.temperature,
                    sampling_params.top_p,
                    sampling_params.top_k,
                    sampling_params.min_p,
                    sampling_params.repetition_penalty,
                    sampling_params.presence_penalty,
                    sampling_params.frequency_penalty,
                    seed_info,
                    sampling_params.max_tokens or 0,
                )

                if i == 0:
                    maybe_rate_limit_error = await self._maybe_reserve_rate_limit(
                        user_id, sampling_params
                    )
                    if maybe_rate_limit_error is not None:
                        return maybe_rate_limit_error
                prompt_length_error = self._validate_request_size(
                    request,
                    prompt_token_count=len(engine_prompt["prompt_token_ids"]),
                )
                if prompt_length_error is not None:
                    return prompt_length_error

                trace_headers = (
                    None
                    if raw_request is None
                    else await self._get_trace_headers(raw_request.headers)
                )
                request_trace_headers = trace_headers

                context: ConversationContext
                if self.use_harmony:
                    if request.stream:
                        context = StreamingHarmonyContext(messages, available_tools)
                    else:
                        context = HarmonyContext(messages, available_tools)
                else:
                    context = SimpleContext()

                if self.reasoning_parser is not None:
                    reasoning_parser = self.reasoning_parser(tokenizer)
                    if sampling_params.structured_outputs is None:
                        sampling_params.structured_outputs = StructuredOutputsParams()
                    struct_out = sampling_params.structured_outputs
                    if struct_out.all_non_structural_tag_constraints_none():
                        sampling_params.structured_outputs.structural_tag = (
                            reasoning_parser.prepare_structured_tag(
                                sampling_params.structured_outputs.structural_tag,
                                self.tool_server,
                            )
                        )
                generator = self._generate_with_builtin_tools(
                    request_id=request.request_id,
                    request_prompt=request_prompts[i],
                    engine_prompt=engine_prompt,
                    sampling_params=sampling_params,
                    context=context,
                    lora_request=lora_request,
                    priority=request.priority,
                    trace_headers=trace_headers,
                )
                generators.append(generator)
        except ValueError as e:
            # TODO: Use a vllm-specific Validation Error
            return self.create_error_response(str(e))

        assert len(generators) == 1
        (result_generator,) = generators

        # Store the input messages.
        if request.store:
            self.msg_store[request.request_id] = messages
            await self._record_input_items(request)

        if request.background:
            created_time = int(time.time())
            response = ResponsesResponse.from_request(
                request,
                sampling_params,
                model_name=model_name,
                created_time=created_time,
                output=[],
                status="queued",
                usage=None,
            )
            await self._store_response_object(response)

            if request.stream:
                self._start_stream_response_task(
                    request,
                    sampling_params,
                    result_generator,
                    context,
                    model_name,
                    tokenizer,
                    request_metadata,
                    created_time,
                    lora_request=lora_request,
                    trace_headers=request_trace_headers,
                    priority=request.priority,
                )
            else:
                task = asyncio.create_task(
                    self._run_background_request(
                        request,
                        sampling_params,
                        result_generator,
                        context,
                        model_name,
                        tokenizer,
                        request_metadata,
                        created_time,
                    ),
                    name=f"create_{response.id}",
                )
                self.background_tasks[response.id] = task
                task.add_done_callback(
                    lambda _: self.background_tasks.pop(response.id, None)
                )

            if request.stream:
                return self.responses_background_stream_generator(request.request_id)
            return response

        if request.stream:
            created_time = int(time.time())
            self._start_stream_response_task(
                request,
                sampling_params,
                result_generator,
                context,
                model_name,
                tokenizer,
                request_metadata,
                created_time,
                lora_request=lora_request,
                trace_headers=request_trace_headers,
                priority=request.priority,
            )
            return self.responses_background_stream_generator(request.request_id)

        try:
            return await self.responses_full_generator(
                request,
                sampling_params,
                result_generator,
                context,
                model_name,
                tokenizer,
                request_metadata,
            )
        except Exception as e:
            return self.create_error_response(str(e))

    async def _make_request(
        self,
        request: ResponsesRequest,
        prev_response: ResponsesResponse | None,
        tokenizer: AnyTokenizer,
    ):
        if request.tools is None or (
            request.tool_choice == "none" and self.exclude_tools_when_tool_choice_none
        ):
            tool_dicts = None
        else:
            tool_dicts = [
                convert_tool_responses_to_completions_format(tool.model_dump())
                for tool in request.tools
            ]
        # Construct the input messages.
        messages = self._construct_input_messages(request, prev_response)
        _, request_prompts, engine_prompts = await self._preprocess_chat(
            request,
            tokenizer,
            messages,
            tool_dicts=tool_dicts,
            tool_parser=self.tool_parser,
            chat_template=self.chat_template,
            chat_template_content_format=self.chat_template_content_format,
        )
        return messages, request_prompts, engine_prompts

    def _normalize_request_tools(self, request: ResponsesRequest) -> None:
        if not request.tools:
            request.tools = []
            return
        normalized: list[Tool] = []
        for tool in request.tools:
            normalized.append(self._convert_tool_to_responses_tool(tool))
        request.tools = normalized

    @staticmethod
    def _convert_tool_to_responses_tool(tool: Any) -> Tool:
        if hasattr(tool, "model_dump"):
            raw = tool.model_dump()
        elif isinstance(tool, Mapping):
            raw = dict(tool)
        else:
            raise ValueError("Unsupported tool schema")
        if raw.get("type") == "function" and isinstance(raw.get("function"), Mapping):
            function_data = raw["function"]
            flat: dict[str, Any] = {
                "type": "function",
                "name": function_data.get("name"),
                "description": function_data.get("description"),
                "parameters": function_data.get("parameters"),
            }
            if "strict" in function_data:
                flat["strict"] = function_data.get("strict")
            raw = flat
        try:
            return TOOL_VALIDATOR.validate_python(raw)
        except ValidationError as exc:
            raise ValueError("Unsupported tool schema") from exc

    def _make_request_with_harmony(
        self,
        request: ResponsesRequest,
        prev_response: ResponsesResponse | None,
    ):
        if request.tool_choice != "auto":
            raise NotImplementedError(
                "Only 'auto' tool_choice is supported in response API with Harmony"
            )
        messages = self._construct_input_messages_with_harmony(request, prev_response)
        prompt_token_ids = render_for_completion(messages)
        engine_prompt = EngineTokensPrompt(prompt_token_ids=prompt_token_ids)

        # Add cache_salt if provided in the request
        if request.cache_salt is not None:
            engine_prompt["cache_salt"] = request.cache_salt

        return messages, [prompt_token_ids], [engine_prompt]

    async def _initialize_tool_sessions(
        self,
        request: ResponsesRequest,
        context: ConversationContext,
        exit_stack: AsyncExitStack,
    ):
        # we should only initialize the tool session if the request needs tools
        if len(request.tools) == 0:
            return
        mcp_tools = {
            tool.server_label: tool for tool in request.tools if tool.type == "mcp"
        }
        await context.init_tool_sessions(
            self.tool_server, exit_stack, request.request_id, mcp_tools
        )

    async def responses_full_generator(
        self,
        request: ResponsesRequest,
        sampling_params: SamplingParams,
        result_generator: AsyncIterator[ConversationContext],
        context: ConversationContext,
        model_name: str,
        tokenizer: AnyTokenizer,
        request_metadata: RequestResponseMetadata,
        created_time: int | None = None,
    ) -> ErrorResponse | ResponsesResponse:
        if created_time is None:
            created_time = int(time.time())

        async with AsyncExitStack() as exit_stack:
            try:
                await self._initialize_tool_sessions(request, context, exit_stack)
                async for _ in result_generator:
                    pass
            except asyncio.CancelledError:
                return self.create_error_response("Client disconnected")
            except ValueError as e:
                # TODO: Use a vllm-specific Validation Error
                return self.create_error_response(str(e))

        # NOTE: Implementation of stauts is still WIP, but for now
        # we guarantee that if the status is not "completed", it is accurate.
        # "completed" is implemented as the "catch-all" for now.
        status: ResponseStatus = "completed"

        input_messages = None
        output_messages = None
        if self.use_harmony:
            assert isinstance(context, HarmonyContext)
            output = self._make_response_output_items_with_harmony(context)
            if request.enable_response_messages:
                input_messages = context.messages[: context.num_init_messages]
                output_messages = context.messages[context.num_init_messages :]
            num_tool_output_tokens = context.num_tool_output_tokens
            if len(output) > 0:
                if context.finish_reason == "length":
                    status = "incomplete"
                elif context.finish_reason == "abort":
                    status = "cancelled"
            else:
                status = "incomplete"
        else:
            assert isinstance(context, SimpleContext)
            final_res = context.last_output
            assert final_res is not None
            assert len(final_res.outputs) == 1
            final_output = final_res.outputs[0]

            output = self._make_response_output_items(request, final_output, tokenizer)

            # TODO: context for non-gptoss models doesn't use messages
            # so we can't get them out yet
            if request.enable_response_messages:
                raise NotImplementedError(
                    "enable_response_messages is currently only supported for gpt-oss"
                )
            # Calculate usage.
            assert final_res.prompt_token_ids is not None
            num_tool_output_tokens = 0

        assert isinstance(context, (SimpleContext, HarmonyContext))
        num_prompt_tokens = context.num_prompt_tokens
        num_generated_tokens = context.num_output_tokens
        num_cached_tokens = context.num_cached_tokens
        num_reasoning_tokens = context.num_reasoning_tokens

        usage = ResponseUsage(
            input_tokens=num_prompt_tokens,
            output_tokens=num_generated_tokens,
            total_tokens=num_prompt_tokens + num_generated_tokens,
            input_tokens_details=InputTokensDetails(
                cached_tokens=num_cached_tokens,
                input_tokens_per_turn=[
                    turn.input_tokens for turn in context.all_turn_metrics
                ],
                cached_tokens_per_turn=[
                    turn.cached_input_tokens for turn in context.all_turn_metrics
                ],
            ),
            output_tokens_details=OutputTokensDetails(
                reasoning_tokens=num_reasoning_tokens,
                tool_output_tokens=num_tool_output_tokens,
                output_tokens_per_turn=[
                    turn.output_tokens for turn in context.all_turn_metrics
                ],
                tool_output_tokens_per_turn=[
                    turn.tool_output_tokens for turn in context.all_turn_metrics
                ],
            ),
        )
        response = ResponsesResponse.from_request(
            request,
            sampling_params,
            input_messages=input_messages,
            output_messages=output_messages,
            model_name=model_name,
            created_time=created_time,
            output=output,
            status=status,
            usage=usage,
        )

        if request.store:
            await self._set_or_update_stored_response(response)
        return response

    def _topk_logprobs(
        self,
        logprobs: dict[int, SampleLogprob],
        top_logprobs: int,
        tokenizer: AnyTokenizer,
    ) -> list[LogprobTopLogprob]:
        """Returns the top-k logprobs from the logprobs dictionary."""
        out = []
        for i, (token_id, _logprob) in enumerate(logprobs.items()):
            if i >= top_logprobs:
                break
            text = (
                _logprob.decoded_token
                if _logprob.decoded_token is not None
                else tokenizer.decode([token_id])
            )
            out.append(
                LogprobTopLogprob(
                    token=text,
                    logprob=max(_logprob.logprob, -9999.0),
                    bytes=list(text.encode("utf-8", errors="replace")),
                )
            )
        return out

    def _create_response_logprobs(
        self,
        token_ids: Sequence[int],
        logprobs: SampleLogprobs | None,
        tokenizer: AnyTokenizer,
        top_logprobs: int | None = None,
    ) -> list[Logprob]:
        assert logprobs is not None, "logprobs must be provided"
        assert len(token_ids) == len(logprobs), (
            "token_ids and logprobs.token_ids must have the same length"
        )
        out = []
        for i, token_id in enumerate(token_ids):
            logprob = logprobs[i]
            token_logprob = logprob[token_id]
            text = (
                token_logprob.decoded_token
                if token_logprob.decoded_token is not None
                else tokenizer.decode([token_id])
            )
            out.append(
                Logprob(
                    token=text,
                    logprob=max(token_logprob.logprob, -9999.0),
                    bytes=list(text.encode("utf-8", errors="replace")),
                    top_logprobs=(
                        self._topk_logprobs(
                            logprob, top_logprobs=top_logprobs, tokenizer=tokenizer
                        )
                        if top_logprobs
                        else []
                    ),
                )
            )
        return out

    def _create_stream_response_logprobs(
        self,
        token_ids: Sequence[int],
        logprobs: SampleLogprobs | None,
        tokenizer: AnyTokenizer,
        top_logprobs: int | None = None,
    ) -> list[response_text_delta_event.Logprob]:
        lgs = self._create_response_logprobs(
            token_ids=token_ids,
            logprobs=logprobs,
            tokenizer=tokenizer,
            top_logprobs=top_logprobs,
        )
        return [
            response_text_delta_event.Logprob(
                token=lg.token,
                logprob=lg.logprob,
                top_logprobs=[
                    response_text_delta_event.LogprobTopLogprob(
                        token=tl.token, logprob=tl.logprob
                    )
                    for tl in lg.top_logprobs
                ],
            )
            for lg in lgs
        ]

    def _make_response_output_items(
        self,
        request: ResponsesRequest,
        final_output: CompletionOutput,
        tokenizer: AnyTokenizer,
    ) -> list[ResponseOutputItem]:
        if self.reasoning_parser:
            try:
                reasoning_parser = self.reasoning_parser(tokenizer)
            except RuntimeError as e:
                logger.exception("Error in reasoning parser creation.")
                raise e

            reasoning, content = reasoning_parser.extract_reasoning(
                final_output.text, request=request
            )
        else:
            reasoning = None
            content = final_output.text

        # Log complete response if output logging is enabled
        if self.enable_log_outputs and self.request_logger:
            output_text = ""
            if content:
                output_text = content
            elif reasoning:
                output_text = f"[reasoning: {reasoning}]"

            if output_text:
                self.request_logger.log_outputs(
                    request_id=request.request_id,
                    outputs=output_text,
                    output_token_ids=final_output.token_ids,
                    finish_reason=final_output.finish_reason,
                    is_streaming=False,
                    delta=False,
                )

        reasoning_item = None
        message_item = None
        if reasoning:
            reasoning_item = ResponseReasoningItem(
                id=f"rs_{random_uuid()}",
                summary=[],
                type="reasoning",
                content=[
                    ResponseReasoningTextContent(text=reasoning, type="reasoning_text")
                ],
                status=None,  # NOTE: Only the last output item has status.
            )
        tool_calls, content = self._parse_tool_calls_from_content(
            request=request,
            tokenizer=tokenizer,
            content=content,
            enable_auto_tools=self.enable_auto_tools,
            tool_parser_cls=self.tool_parser,
        )
        if content:
            output_text = ResponseOutputText(
                text=content,
                annotations=[],  # TODO
                type="output_text",
                logprobs=(
                    self._create_response_logprobs(
                        token_ids=final_output.token_ids,
                        logprobs=final_output.logprobs,
                        tokenizer=tokenizer,
                        top_logprobs=request.top_logprobs,
                    )
                    if request.is_include_output_logprobs()
                    else None
                ),
            )
            message_item = ResponseOutputMessage(
                id=f"msg_{random_uuid()}",
                content=[output_text],
                role="assistant",
                status="completed",
                type="message",
            )
        outputs = []

        if reasoning_item:
            outputs.append(reasoning_item)
        if message_item:
            outputs.append(message_item)
        if tool_calls:
            tool_call_items = [
                ResponseFunctionToolCall(
                    id=f"fc_{random_uuid()}",
                    call_id=f"call_{random_uuid()}",
                    type="function_call",
                    status="completed",
                    name=tool_call.name,
                    arguments=tool_call.arguments,
                )
                for tool_call in tool_calls
            ]
            outputs.extend(tool_call_items)
        return outputs

    def _make_response_output_items_with_harmony(
        self,
        context: HarmonyContext,
    ) -> list[ResponseOutputItem]:
        output_items: list[ResponseOutputItem] = []
        num_init_messages = context.num_init_messages
        for msg in context.messages[num_init_messages:]:
            output_items.extend(parse_output_message(msg))
        # Handle the generation stopped in the middle (if any).
        last_items = parse_remaining_state(context.parser)
        if last_items:
            output_items.extend(last_items)
        return output_items

    def _construct_input_messages(
        self,
        request: ResponsesRequest,
        prev_response: ResponsesResponse | None = None,
    ) -> list[ChatCompletionMessageParam]:
        messages: list[ChatCompletionMessageParam] = []
        if request.instructions:
            messages.append(
                {
                    "role": "system",
                    "content": request.instructions,
                }
            )

        # Prepend the conversation history.
        if prev_response is not None:
            # Add the previous messages.
            prev_msg = self.msg_store[prev_response.id]
            messages.extend(prev_msg)

            # Add the previous output.
            for output_item in prev_response.output:
                # NOTE: We skip the reasoning output.
                if isinstance(output_item, ResponseOutputMessage):
                    for content in output_item.content:
                        messages.append(
                            {
                                "role": "assistant",
                                "content": content.text,
                            }
                        )

        # Append the new input.
        # Responses API supports simple text inputs without chat format.
        if isinstance(request.input, str):
            messages.append({"role": "user", "content": request.input})
        else:
            for item in request.input:
                messages.append(construct_chat_message_with_tool_call(item))
        return messages

    def _construct_harmony_system_input_message(
        self, request: ResponsesRequest, with_custom_tools: bool, tool_types: set[str]
    ) -> OpenAIHarmonyMessage:
        reasoning_effort = request.reasoning.effort if request.reasoning else None
        enable_browser = (
            "web_search_preview" in tool_types
            and self.tool_server is not None
            and self.tool_server.has_tool("browser")
        )
        enable_code_interpreter = (
            "code_interpreter" in tool_types
            and self.tool_server is not None
            and self.tool_server.has_tool("python")
        )
        enable_container = (
            "container" in tool_types
            and self.tool_server is not None
            and self.tool_server.has_tool("container")
        )
        sys_msg = get_system_message(
            reasoning_effort=reasoning_effort,
            browser_description=(
                self.tool_server.get_tool_description("browser")
                if enable_browser and self.tool_server is not None
                else None
            ),
            python_description=(
                self.tool_server.get_tool_description("python")
                if enable_code_interpreter and self.tool_server is not None
                else None
            ),
            container_description=(
                self.tool_server.get_tool_description("container")
                if enable_container and self.tool_server is not None
                else None
            ),
            instructions=request.instructions,
            with_custom_tools=with_custom_tools,
        )
        return sys_msg

    def _construct_input_messages_with_harmony(
        self,
        request: ResponsesRequest,
        prev_response: ResponsesResponse | None,
    ) -> list[OpenAIHarmonyMessage]:
        messages: list[OpenAIHarmonyMessage] = []
        if prev_response is None:
            # New conversation.
            tool_types = extract_tool_types(request.tools)
            with_custom_tools = has_custom_tools(tool_types)

            sys_msg = self._construct_harmony_system_input_message(
                request, with_custom_tools, tool_types
            )
            messages.append(sys_msg)
            if with_custom_tools:
                dev_msg = get_developer_message(
                    instructions=request.instructions, tools=request.tools
                )
                messages.append(dev_msg)
            messages += construct_harmony_previous_input_messages(request)

        else:
            # Continue the previous conversation.
            # FIXME(woosuk): Currently, request params like reasoning and
            # instructions are ignored.
            prev_msgs = self.msg_store[prev_response.id]
            # Remove the previous chain-of-thoughts if there is a new "final"
            # message. Note that this also removes these messages from the
            # msg_store.
            if len(prev_msgs) > 0:
                last_msg = prev_msgs[-1]
                assert isinstance(last_msg, OpenAIHarmonyMessage)
                if last_msg.channel == "final":
                    prev_final_msg_idx = -1
                    for i in range(len(prev_msgs) - 2, -1, -1):
                        prev_msg_i = prev_msgs[i]
                        assert isinstance(prev_msg_i, OpenAIHarmonyMessage)
                        if prev_msg_i.channel == "final":
                            prev_final_msg_idx = i
                            break
                    recent_turn_msgs = prev_msgs[prev_final_msg_idx + 1 :]
                    del prev_msgs[prev_final_msg_idx + 1 :]
                    for msg in recent_turn_msgs:
                        assert isinstance(msg, OpenAIHarmonyMessage)
                        if msg.channel != "analysis":
                            prev_msgs.append(msg)
            messages.extend(prev_msgs)
        # Append the new input.
        # Responses API supports simple text inputs without chat format.
        if isinstance(request.input, str):
            messages.append(get_user_message(request.input))
        else:
            if prev_response is not None:
                prev_outputs = copy(prev_response.output)
            else:
                prev_outputs = []
            for response_msg in request.input:
                messages.append(parse_response_input(response_msg, prev_outputs))
                # User passes in a tool call request and its output. We need
                # to add the tool call request to prev_outputs so that the
                # parse_response_input can find the tool call request when
                # parsing the tool call output.
                if isinstance(response_msg, ResponseFunctionToolCall):
                    prev_outputs.append(response_msg)
        return messages

    def _start_stream_response_task(
        self,
        request: ResponsesRequest,
        sampling_params: SamplingParams,
        result_generator: AsyncIterator[ConversationContext | None],
        context: ConversationContext,
        model_name: str,
        tokenizer: AnyTokenizer,
        request_metadata: RequestResponseMetadata,
        created_time: int,
        *,
        lora_request: LoRARequest | None,
        trace_headers: Mapping[str, str] | None,
        priority: int,
    ) -> None:
        event_deque: deque[StreamingResponsesResponse] = deque()
        new_event_signal = asyncio.Event()
        stream_state = ResponseStreamSession(
            request=request,
            sampling_params=sampling_params,
            context=context,
            model_name=model_name,
            tokenizer=tokenizer,
            request_metadata=request_metadata,
            lora_request=lora_request,
            trace_headers=trace_headers,
            priority=priority,
            current_generator=result_generator,
        )
        session = ResponseSession(
            id=request.request_id,
            request=request,
            sampling_params=sampling_params,
            context=context,
            model_name=model_name,
            tokenizer=tokenizer,
            request_metadata=request_metadata,
            created_time=created_time,
            event_deque=event_deque,
            new_event_signal=new_event_signal,
            generator=result_generator,
            stream_state=stream_state,
            user_id=request.user or "anonymous",
        )
        self.session_manager.add_session(session)

        async def _producer():
            await self._produce_stream_events(
                request,
                sampling_params,
                result_generator,
                context,
                model_name,
                tokenizer,
                request_metadata,
                created_time,
                event_deque,
                new_event_signal,
                session=session,
            )

        task = asyncio.create_task(
            _producer(),
            name=f"create_{request.request_id}",
        )
        self.background_tasks[request.request_id] = task
        session.background_task = task
        task.add_done_callback(
            lambda _: self.background_tasks.pop(request.request_id, None)
        )

    def _build_streaming_error_event(
        self,
        response_id: str,
        error_response: ErrorResponse,
        event_deque: deque[StreamingResponsesResponse],
    ) -> ResponseErrorEvent:
        """Create a ResponseErrorEvent that continues the stream sequence."""

        next_sequence_number = 0
        if event_deque:
            last_event = event_deque[-1]
            last_sequence = getattr(last_event, "sequence_number", None)
            if isinstance(last_sequence, int) and last_sequence >= 0:
                next_sequence_number = last_sequence + 1

        response_payload: dict[str, Any] = {"status": "failed"}
        if response_id:
            response_payload["id"] = response_id

        return ResponseErrorEvent(
            type="response.error",
            response=response_payload,
            error=error_response.error,
            sequence_number=next_sequence_number,
        )

    def _estimate_stream_event_bytes(
        self, event: StreamingResponsesResponse
    ) -> int:
        serialized = event.model_dump_json(indent=None)
        return len(serialized.encode("utf-8"))

    def _record_stream_event_metrics(
        self,
        session: ResponseSession,
        event: StreamingResponsesResponse,
        *,
        response_id: str,
        enforce_event_limit: bool = True,
        enforce_buffer_limit: bool = True,
    ) -> None:
        event_size = self._estimate_stream_event_bytes(event)
        if (
            enforce_event_limit
            and self.max_stream_event_bytes is not None
            and event_size > self.max_stream_event_bytes
        ):
            logger.warning(
                (
                    "Streaming event for response %s exceeded per-event limit: "
                    "%d bytes > %d bytes."
                ),
                response_id,
                event_size,
                self.max_stream_event_bytes,
            )
            raise ValueError(
                (
                    f"Streaming event exceeds max_stream_event_bytes "
                    f"({event_size} > {self.max_stream_event_bytes})."
                )
            )

        projected_total = session.event_queue_bytes + event_size
        if (
            enforce_buffer_limit
            and self.responses_stream_buffer_max_bytes is not None
            and projected_total > self.responses_stream_buffer_max_bytes
        ):
            logger.warning(
                (
                    "Streaming session %s exceeded buffer limit: "
                    "%d bytes > %d bytes."
                ),
                response_id,
                projected_total,
                self.responses_stream_buffer_max_bytes,
            )
            raise OverflowError(
                (
                    "Streaming buffer exceeded responses_stream_buffer_max_bytes "
                    f"({projected_total} > {self.responses_stream_buffer_max_bytes})."
                )
            )

        session.event_queue_bytes = projected_total

    async def _await_tool_outputs(
        self, session: ResponseStreamSession
    ) -> AsyncIterator[ConversationContext | None]:
        """Wait for external tool outputs to arrive before resuming generation."""

        logger.debug(
            "Response %s waiting for tool outputs (timeout=%ds)...",
            session.request.request_id,
            self.tool_outputs_timeout,
        )
        session.resume_event.clear()
        session.waiting_for_tool_outputs = True
        try:
            await asyncio.wait_for(
                session.resume_event.wait(),
                timeout=self.tool_outputs_timeout,
            )
        except asyncio.TimeoutError as exc:
            session.waiting_for_tool_outputs = False
            logger.warning(
                "Timed out waiting for tool outputs for response %s",
                session.request.request_id,
            )
            raise TimeoutError("Timed out waiting for tool outputs") from exc
        session.waiting_for_tool_outputs = False
        logger.debug(
            "Response %s received tool outputs, resuming generation...",
            session.request.request_id,
        )

        if session.current_generator is None:
            raise RuntimeError("Tool outputs arrived, but no generator to resume.")
        return session.current_generator

    def _convert_tool_outputs_to_message(
        self,
        pending_call: PendingToolCallState,
        payload: ResponsesToolOutputsRequest,
    ) -> OpenAIHarmonyMessage:
        output_payload = [
            item.model_dump(exclude_none=True) for item in payload.output
        ]
        tool_output_item: ResponseInputOutputItem = {
            "type": "function_call_output",
            "call_id": pending_call.tool_call.call_id,
            "output": output_payload,
        }
        return parse_response_input(tool_output_item, [pending_call.tool_call])

    def _resume_session_after_tool_call(
        self, session: ResponseStreamSession
    ) -> None:
        if not isinstance(session.context, (HarmonyContext, StreamingHarmonyContext)):
            raise RuntimeError(
                "tool_outputs continuation is only supported for Harmony contexts."
            )

        prompt_token_ids = session.context.render_for_completion()
        engine_prompt = EngineTokensPrompt(prompt_token_ids=prompt_token_ids)
        session.sampling_params.max_tokens = (
            self.max_model_len - len(prompt_token_ids)
        )
        session.priority -= 1
        session.current_generator = self._generate_with_builtin_tools(
            request_id=session.request.request_id,
            request_prompt=prompt_token_ids,
            engine_prompt=engine_prompt,
            sampling_params=session.sampling_params,
            context=session.context,
            lora_request=session.lora_request,
            priority=session.priority,
            trace_headers=session.trace_headers,
        )
        session.resume_event.set()

    async def submit_tool_outputs(
        self,
        response_id: str,
        payload: ResponsesToolOutputsRequest,
    ) -> ErrorResponse | dict[str, str]:
        if self.max_tool_output_bytes is not None:
            approx_size = len(payload.model_dump_json().encode("utf-8"))
            if approx_size > self.max_tool_output_bytes:
                logger.warning(
                    "tool_outputs payload exceeded %d bytes (response %s)",
                    self.max_tool_output_bytes,
                    response_id,
                )
                return self.create_error_response(
                    err_type="invalid_request_error",
                    message=(
                        f"tool_outputs payload exceeds limit "
                        f"{self.max_tool_output_bytes} bytes."
                    ),
                    status_code=HTTPStatus.BAD_REQUEST,
                )
        response_session = self.session_manager.get_session(response_id)
        if response_session is None or response_session.stream_state is None:
            return self._make_not_found_error(response_id)

        session = response_session.stream_state
        if not payload.output:
            return self.create_error_response(
                err_type="invalid_request_error",
                message="`output` must contain at least one item.",
                status_code=HTTPStatus.BAD_REQUEST,
            )

        async with session.lock:
            pending_call = session.pending_tool_calls.get(payload.tool_call_id)
            if pending_call is None:
                logger.warning(
                    "tool_outputs for unknown call_id %s (response %s)",
                    payload.tool_call_id,
                    response_id,
                )
                return self.create_error_response(
                    err_type="invalid_request_error",
                    message=(
                        f"Unknown tool_call_id '{payload.tool_call_id}' for "
                        f"response '{response_id}'."
                    ),
                    status_code=HTTPStatus.NOT_FOUND,
                )
            if pending_call.output is not None:
                logger.warning(
                    "Duplicate tool_outputs for call_id %s (response %s)",
                    payload.tool_call_id,
                    response_id,
                )
                return self.create_error_response(
                    err_type="invalid_request_error",
                    message=f"tool_call_id '{payload.tool_call_id}' already completed.",
                    status_code=HTTPStatus.BAD_REQUEST,
                )
            if not session.waiting_for_tool_outputs:
                logger.warning(
                    "tool_outputs unexpected for response %s (no pending wait)",
                    response_id,
                )
                return self.create_error_response(
                    err_type="invalid_request_error",
                    message="No pending tool outputs expected for this response.",
                    status_code=HTTPStatus.BAD_REQUEST,
                )

            if not session.waiting_for_tool_outputs and not session.has_pending_tool_calls():
                return self.create_error_response(
                    err_type="invalid_request_error",
                    message="Response is not waiting for tool outputs.",
                    status_code=HTTPStatus.BAD_REQUEST,
                )

            harmony_message = self._convert_tool_outputs_to_message(
                pending_call, payload
            )
            session.context.append_tool_output([harmony_message])
            pending_call.output = [item.model_dump() for item in payload.output]
            session.pop_tool_call(payload.tool_call_id)

            should_resume = not session.has_pending_tool_calls()
            if should_resume:
                self._resume_session_after_tool_call(session)

        return {"id": response_id, "status": "in_progress"}

    async def _produce_stream_events(
        self,
        request: ResponsesRequest,
        sampling_params: SamplingParams,
        result_generator: AsyncIterator[ConversationContext | None],
        context: ConversationContext,
        model_name: str,
        tokenizer: AnyTokenizer,
        request_metadata: RequestResponseMetadata,
        created_time: int,
        event_deque: deque[StreamingResponsesResponse],
        new_event_signal: asyncio.Event,
        session: ResponseSession,
    ) -> None:
        error_response: ErrorResponse | None = None
        try:
            generator = self.responses_stream_generator(
                request,
                sampling_params,
                result_generator,
                context,
                model_name,
                tokenizer,
                request_metadata,
                created_time=created_time,
                session=session.stream_state,
            )
            async for event in generator:
                self._record_stream_event_metrics(
                    session,
                    event,
                    response_id=request.request_id,
                )
                event_deque.append(event)
                new_event_signal.set()
        except asyncio.CancelledError:
            logger.info(
                "Streaming request cancelled for %s before completion.",
                request.request_id,
            )
            raise
        except Exception as e:
            logger.exception("Streaming request failed for %s", request.request_id)
            error_response = self.create_error_response(str(e))
            error_event = self._build_streaming_error_event(
                request.request_id, error_response, event_deque
            )
            try:
                self._record_stream_event_metrics(
                    session,
                    error_event,
                    response_id=request.request_id,
                    enforce_event_limit=False,
                    enforce_buffer_limit=False,
                )
            except Exception:
                logger.exception(
                    "Failed to measure error event for %s", request.request_id
                )
            event_deque.append(error_event)
            new_event_signal.set()
        finally:
            new_event_signal.set()
            session.stream_state = None
            session.background_task = None
            session.generator = result_generator
            session.mark_completed()
            self.session_manager.cleanup_expired_sessions()

        if error_response is not None and request.store:
            await self._update_stored_response_status(
                request.request_id, status="failed"
            )

    async def _run_background_request(
        self,
        request: ResponsesRequest,
        *args,
        **kwargs,
    ):
        try:
            response = await self.responses_full_generator(request, *args, **kwargs)
        except Exception as e:
            logger.exception("Background request failed for %s", request.request_id)
            response = self.create_error_response(str(e))

        if isinstance(response, ErrorResponse):
            await self._update_stored_response_status(
                request.request_id, status="failed"
            )

    async def responses_background_stream_generator(
        self,
        response_id: str,
        starting_after: int | None = None,
    ) -> AsyncGenerator[StreamingResponsesResponse, None]:
        session = self.session_manager.get_session(response_id)
        if session is None:
            raise ValueError(f"Unknown response_id: {response_id}")

        event_deque = session.event_deque
        new_event_signal = session.new_event_signal
        start_index = 0 if starting_after is None else starting_after + 1
        current_index = start_index

        while True:
            new_event_signal.clear()

            # Yield existing events from start_index
            while current_index < len(event_deque):
                event = event_deque[current_index]
                yield event
                if getattr(event, "type", "unknown") == "response.completed":
                    return
                current_index += 1

            if session.completed:
                return

            await new_event_signal.wait()

    async def retrieve_responses(
        self,
        response_id: str,
        starting_after: int | None,
        stream: bool | None,
    ) -> (
        ErrorResponse
        | ResponsesResponse
        | AsyncGenerator[StreamingResponsesResponse, None]
    ):
        session = self.session_manager.get_session(response_id)
        stored_response = await self._get_stored_response(response_id)

        if stream:
            if session is not None:
                return self.responses_background_stream_generator(
                    response_id,
                    starting_after,
                )
            return self._make_not_found_error(response_id)

        if stored_response is not None:
            return stored_response
        return self._make_not_found_error(response_id)

    async def cancel_responses(
        self,
        response_id: str,
    ) -> ErrorResponse | ResponsesResponse:
        response = await self._get_stored_response(response_id)
        if response is None:
            return self._make_not_found_error(response_id)

        prev_status = response.status
        if prev_status not in ("queued", "in_progress"):
            return self.create_error_response(
                err_type="invalid_request_error",
                message="Cannot cancel a synchronous response.",
            )

        response.status = "cancelled"
        await self._update_stored_response_status(response_id, status="cancelled")

        # Abort the request.
        if task := self.background_tasks.get(response_id):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                logger.exception("Background task for %s was cancelled", response_id)
        self.session_manager.remove_session(response_id)
        return response

    async def handle_stream_disconnect(
        self,
        response_id: str,
        *,
        reason: str = "client_disconnect",
    ) -> None:
        """Cleanup state and background tasks after SSE client disconnects."""

        session = self.session_manager.remove_session(response_id)
        if session is None:
            return

        logger.info(
            "Cleaning up streaming session %s after %s.",
            response_id,
            reason,
        )

        task = self.background_tasks.pop(response_id, None)
        if task is None:
            task = session.background_task

        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                logger.debug(
                    "Background streaming task for %s cancelled during %s.",
                    response_id,
                    reason,
                )

    def _make_not_found_error(self, response_id: str) -> ErrorResponse:
        return self.create_error_response(
            err_type="invalid_request_error",
            message=f"Response with id '{response_id}' not found.",
            status_code=HTTPStatus.NOT_FOUND,
        )

    def _make_store_not_supported_error(self) -> ErrorResponse:
        return self.create_error_response(
            err_type="invalid_request_error",
            message=(
                "`store=True` is disabled on this server. Enable storage by "
                "removing `--disable-responses-store` or setting "
                "`VLLM_ENABLE_RESPONSES_API_STORE=1` when launching vLLM."
            ),
            status_code=HTTPStatus.BAD_REQUEST,
        )

    async def _record_input_items(self, request: ResponsesRequest) -> None:
        if not (self.enable_store and request.store):
            return
        normalized = self._normalize_input_items(request.input)
        async with self.response_store_lock:
            self.response_input_items[request.request_id] = normalized

    def _normalize_input_items(
        self, request_input: str | list[ResponseInputOutputItem]
    ) -> list[dict[str, Any]]:
        if isinstance(request_input, str):
            return [
                {
                    "id": f"msg_{random_uuid()}",
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": request_input,
                        }
                    ],
                }
            ]
        if not isinstance(request_input, list):
            return []
        normalized_items: list[dict[str, Any]] = []
        for index, item in enumerate(request_input):
            payload = self._serialize_input_item(item)
            if not payload.get("id"):
                payload["id"] = f"item_{index}_{random_uuid()}"
            if "type" not in payload and "role" in payload:
                payload["type"] = "message"
            normalized_items.append(payload)
        return normalized_items

    @staticmethod
    def _serialize_input_item(item: ResponseInputOutputItem | Any) -> dict[str, Any]:
        if hasattr(item, "model_dump"):
            return item.model_dump(exclude_none=True)
        if isinstance(item, dict):
            return deepcopy(item)
        if hasattr(item, "__dict__"):
            return deepcopy(item.__dict__)
        return {"value": item}

    async def list_response_input_items(
        self,
        response_id: str,
        *,
        limit: int,
        order: str,
        after: str | None = None,
        include: list[str] | None = None,
    ) -> ErrorResponse | tuple[dict[str, Any], str | None]:
        if not self.enable_store:
            return self._make_store_not_supported_error()
        stored_response = await self._get_stored_response(response_id)
        if stored_response is None:
            return self._make_not_found_error(response_id)
        if include:
            return self.create_error_response(
                err_type="invalid_request_error",
                message="`include` is not supported for input_items.",
                status_code=HTTPStatus.BAD_REQUEST,
            )
        normalized_order = order.lower()
        if normalized_order not in {"asc", "desc"}:
            return self.create_error_response(
                err_type="invalid_request_error",
                message="`order` must be either 'asc' or 'desc'.",
                status_code=HTTPStatus.BAD_REQUEST,
            )
        async with self.response_store_lock:
            stored_items = self.response_input_items.get(response_id)
        if stored_items is None:
            return self._make_not_found_error(response_id)
        ordered_items = (
            list(stored_items)
            if normalized_order == "asc"
            else list(reversed(stored_items))
        )
        start_index = 0
        if after is not None:
            for idx, item in enumerate(ordered_items):
                if item.get("id") == after:
                    start_index = idx + 1
                    break
            else:
                return self.create_error_response(
                    err_type="invalid_request_error",
                    message="`after` does not match any input item id.",
                    status_code=HTTPStatus.BAD_REQUEST,
                )
        sliced_items = ordered_items[start_index : start_index + limit]
        has_more = (start_index + len(sliced_items)) < len(ordered_items)
        payload = {
            "object": "list",
            "data": [deepcopy(item) for item in sliced_items],
            "first_id": sliced_items[0]["id"] if sliced_items else None,
            "last_id": sliced_items[-1]["id"] if sliced_items else None,
            "has_more": has_more,
        }
        return payload, stored_response.user

    async def _process_simple_streaming_events(
        self,
        request: ResponsesRequest,
        sampling_params: SamplingParams,
        result_generator: AsyncIterator[ConversationContext | None],
        context: ConversationContext,
        model_name: str,
        tokenizer: AnyTokenizer,
        request_metadata: RequestResponseMetadata,
        created_time: int,
        _increment_sequence_number_and_return: Callable[
            [StreamingResponsesResponse], StreamingResponsesResponse
        ],
        session: ResponseStreamSession | None = None,
    ) -> AsyncGenerator[StreamingResponsesResponse, None]:
        current_content_index = 0
        current_output_index = 0
        current_item_id = ""
        reasoning_parser = None
        include_code_outputs = self._request_includes(
            request, "code_interpreter_call.outputs"
        )
        include_file_search_results = self._request_includes(
            request, "file_search_call.results"
        )
        if self.reasoning_parser:
            reasoning_parser = self.reasoning_parser(tokenizer)
        previous_text = ""
        previous_token_ids: list[int] = []
        first_delta_sent = False
        previous_delta_messages: list[DeltaMessage] = []
        async for ctx in result_generator:
            assert isinstance(ctx, SimpleContext)
            if ctx.last_output is None:
                continue
            if ctx.last_output.outputs:
                output = ctx.last_output.outputs[0]
                if reasoning_parser:
                    delta_message = reasoning_parser.extract_reasoning_streaming(
                        previous_text=previous_text,
                        current_text=previous_text + output.text,
                        delta_text=output.text,
                        previous_token_ids=previous_token_ids,
                        current_token_ids=previous_token_ids + output.token_ids,
                        delta_token_ids=output.token_ids,
                    )
                else:
                    delta_message = DeltaMessage(
                        content=output.text,
                    )
                previous_text += output.text
                previous_token_ids += output.token_ids
                if not delta_message:
                    continue
                if not first_delta_sent:
                    current_item_id = str(uuid.uuid4())
                    if delta_message.reasoning:
                        yield _increment_sequence_number_and_return(
                            ResponseOutputItemAddedEvent(
                                type="response.output_item.added",
                                sequence_number=-1,
                                output_index=current_output_index,
                                item=ResponseReasoningItem(
                                    type="reasoning",
                                    id=current_item_id,
                                    summary=[],
                                    status="in_progress",
                                ),
                            )
                        )
                    else:
                        yield _increment_sequence_number_and_return(
                            ResponseOutputItemAddedEvent(
                                type="response.output_item.added",
                                sequence_number=-1,
                                output_index=current_output_index,
                                item=ResponseOutputMessage(
                                    id=current_item_id,
                                    type="message",
                                    role="assistant",
                                    content=[],
                                    status="in_progress",
                                ),
                            )
                        )
                    yield _increment_sequence_number_and_return(
                        ResponseContentPartAddedEvent(
                            type="response.content_part.added",
                            sequence_number=-1,
                            output_index=current_output_index,
                            item_id=current_item_id,
                            content_index=current_content_index,
                            part=ResponseOutputText(
                                type="output_text",
                                text="",
                                annotations=[],
                                logprobs=[],
                            ),
                        )
                    )
                    current_content_index += 1
                    first_delta_sent = True
                # todo(kebe7jun) tool call support

                # check delta message and previous delta message are
                # same as content or reasoning content
                if (
                    previous_delta_messages
                    and previous_delta_messages[-1].reasoning is not None
                    and delta_message.content is not None
                ):
                    # from reasoning to normal content, send done
                    # event for reasoning
                    reason_content = "".join(
                        pm.reasoning
                        for pm in previous_delta_messages
                        if pm.reasoning is not None
                    )
                    for event in self._build_reasoning_done_events(
                        response_id=request.request_id,
                        reasoning_text=reason_content,
                        item_id=current_item_id,
                        output_index=current_output_index,
                        content_index=current_content_index,
                    ):
                        yield _increment_sequence_number_and_return(event)
                    current_content_index = 0
                    for summary_event in self._generate_reasoning_summary_events(
                        response_id=request.request_id,
                        reasoning_text=reason_content,
                        item_id=current_item_id,
                        output_index=current_output_index,
                    ):
                        yield _increment_sequence_number_and_return(summary_event)
                    for context_event in self._generate_additional_context_events(
                        request,
                        response_id=request.request_id,
                        reasoning_text=reason_content,
                    ):
                        yield _increment_sequence_number_and_return(context_event)
                    reasoning_item = ResponseReasoningItem(
                        type="reasoning",
                        content=[
                            ResponseReasoningTextContent(
                                text=reason_content,
                                type="reasoning_text",
                            ),
                        ],
                        status="completed",
                        id=current_item_id,
                        summary=[],
                    )
                    yield _increment_sequence_number_and_return(
                        ResponseOutputItemDoneEvent(
                            type="response.output_item.done",
                            sequence_number=-1,
                            output_index=current_output_index,
                            item=reasoning_item,
                        )
                    )
                    yield _increment_sequence_number_and_return(
                        ResponseOutputItemAddedEvent(
                            type="response.output_item.added",
                            sequence_number=-1,
                            output_index=current_output_index,
                            item=ResponseOutputMessage(
                                id=current_item_id,
                                type="message",
                                role="assistant",
                                content=[],
                                status="in_progress",
                            ),
                        )
                    )
                    current_output_index += 1
                    current_item_id = str(uuid.uuid4())
                    yield _increment_sequence_number_and_return(
                        ResponseContentPartAddedEvent(
                            type="response.content_part.added",
                            sequence_number=-1,
                            output_index=current_output_index,
                            item_id=current_item_id,
                            content_index=current_content_index,
                            part=ResponseOutputText(
                                type="output_text",
                                text="",
                                annotations=[],
                                logprobs=[],
                            ),
                        )
                    )
                    current_content_index += 1
                    # reset previous delta messages
                    previous_delta_messages = []

                if delta_message.reasoning is not None:
                    for event in self._build_reasoning_delta_events(
                        response_id=request.request_id,
                        delta_text=delta_message.reasoning,
                        item_id=current_item_id,
                        output_index=current_output_index,
                        content_index=current_content_index,
                    ):
                        yield _increment_sequence_number_and_return(event)
                elif delta_message.content is not None:
                    yield _increment_sequence_number_and_return(
                        ResponseTextDeltaEvent(
                            type="response.output_text.delta",
                            sequence_number=-1,
                            content_index=current_content_index,
                            output_index=current_output_index,
                            item_id=current_item_id,
                            delta=delta_message.content,
                            logprobs=(
                                self._create_stream_response_logprobs(
                                    token_ids=output.token_ids,
                                    logprobs=output.logprobs,
                                    tokenizer=tokenizer,
                                    top_logprobs=request.top_logprobs,
                                )
                                if request.is_include_output_logprobs()
                                else []
                            ),
                        )
                    )
                current_content_index += 1

                previous_delta_messages.append(delta_message)
        if previous_delta_messages:
            if previous_delta_messages[-1].reasoning is not None:
                reason_content = "".join(
                    pm.reasoning
                    for pm in previous_delta_messages
                    if pm.reasoning is not None
                )
                for event in self._build_reasoning_done_events(
                    response_id=request.request_id,
                    reasoning_text=reason_content,
                    item_id=current_item_id,
                    output_index=current_output_index,
                    content_index=current_content_index,
                ):
                    yield _increment_sequence_number_and_return(event)
                for summary_event in self._generate_reasoning_summary_events(
                    response_id=request.request_id,
                    reasoning_text=reason_content,
                    item_id=current_item_id,
                    output_index=current_output_index,
                ):
                    yield _increment_sequence_number_and_return(summary_event)
                for context_event in self._generate_additional_context_events(
                    request,
                    response_id=request.request_id,
                    reasoning_text=reason_content,
                ):
                    yield _increment_sequence_number_and_return(context_event)
                current_content_index += 1
                reasoning_item = ResponseReasoningItem(
                    type="reasoning",
                    content=[
                        ResponseReasoningTextContent(
                            text=reason_content,
                            type="reasoning_text",
                        ),
                    ],
                    status="completed",
                    id=current_item_id,
                    summary=[],
                )
                yield _increment_sequence_number_and_return(
                    ResponseOutputItemDoneEvent(
                        type="response.output_item.done",
                        sequence_number=-1,
                        output_index=current_output_index,
                        item=reasoning_item,
                    )
                )
            elif previous_delta_messages[-1].content is not None:
                final_content = "".join(
                    pm.content
                    for pm in previous_delta_messages
                    if pm.content is not None
                )
                yield _increment_sequence_number_and_return(
                    ResponseTextDoneEvent(
                        type="response.output_text.done",
                        sequence_number=-1,
                        output_index=current_output_index,
                        content_index=current_content_index,
                        text=final_content,
                        logprobs=[],
                        item_id=current_item_id,
                    )
                )
                current_content_index += 1
                part = ResponseOutputText(
                    text=final_content,
                    type="output_text",
                    annotations=[],
                )
                yield _increment_sequence_number_and_return(
                    ResponseContentPartDoneEvent(
                        type="response.content_part.done",
                        sequence_number=-1,
                        item_id=current_item_id,
                        output_index=current_output_index,
                        content_index=current_content_index,
                        part=part,
                    )
                )
                current_content_index += 1
                item = ResponseOutputMessage(
                    type="message",
                    role="assistant",
                    content=[
                        part,
                    ],
                    status="completed",
                    id=current_item_id,
                    summary=[],
                )
                yield _increment_sequence_number_and_return(
                    ResponseOutputItemDoneEvent(
                        type="response.output_item.done",
                        sequence_number=-1,
                        output_index=current_output_index,
                        item=item,
                    )
                )

    async def _process_harmony_streaming_events(
        self,
        request: ResponsesRequest,
        sampling_params: SamplingParams,
        result_generator: AsyncIterator[ConversationContext | None],
        context: ConversationContext,
        model_name: str,
        tokenizer: AnyTokenizer,
        request_metadata: RequestResponseMetadata,
        created_time: int,
        _increment_sequence_number_and_return: Callable[
            [StreamingResponsesResponse], StreamingResponsesResponse
        ],
        session: ResponseStreamSession | None = None,
    ) -> AsyncGenerator[StreamingResponsesResponse, None]:
        current_content_index = -1
        current_output_index = 0
        current_item_id: str = ""
        sent_output_item_added = False
        is_first_function_call_delta = False
        current_tool_arguments = ""
        include_code_outputs = self._request_includes(
            request, "code_interpreter_call.outputs"
        )
        include_file_search_results = self._request_includes(
            request, "file_search_call.results"
        )
        current_tool_call_id: str | None = None
        current_tool_call_name: str | None = None
        async for ctx in result_generator:
            assert isinstance(ctx, StreamingHarmonyContext)

            if ctx.is_expecting_start():
                current_output_index += 1
                sent_output_item_added = False
                is_first_function_call_delta = False
                if len(ctx.parser.messages) > 0:
                    previous_item = ctx.parser.messages[-1]
                    if previous_item.recipient is not None:
                        # Deal with tool call
                        if previous_item.recipient.startswith("functions."):
                            function_name = previous_item.recipient[len("functions.") :]
                            if session is not None:
                                session.finalize_tool_call_arguments(
                                    current_item_id, previous_item.content[0].text
                                )
                            # Save call_id before reset
                            saved_tool_call_id = current_tool_call_id
                            current_tool_arguments = ""
                            # session.finalize already invoked in branch above if needed.
                            current_tool_call_id = None
                            current_tool_call_name = None
                            yield _increment_sequence_number_and_return(
                                ResponseFunctionCallArgumentsDoneEvent(
                                    type="response.function_call_arguments.done",
                                    arguments=previous_item.content[0].text,
                                    name=function_name,
                                    item_id=current_item_id,
                                    output_index=current_output_index,
                                    sequence_number=-1,
                                )
                            )
                            # Notify that the tool call argument stream has
                            # completed so clients (e.g., Codex) can open the
                            # tool gate deterministically.
                            resolved_call_id = (
                                saved_tool_call_id if saved_tool_call_id else f"call_{random_uuid()}"
                            )
                            if logger.isEnabledFor(logging.DEBUG):
                                try:
                                    logger.debug(
                                        "TOOL_CALL completed: response=%s call_id=%s",
                                        request.request_id,
                                        resolved_call_id,
                                    )
                                except Exception:
                                    pass
                            yield _increment_sequence_number_and_return(
                                ResponseToolCallCompletedEvent(
                                    type="response.tool_call.completed",
                                    response={"id": request.request_id},
                                    call_id=resolved_call_id,
                                    sequence_number=-1,
                                )
                            )
                            function_call_item = ResponseFunctionToolCall(
                                type="function_call",
                                arguments=previous_item.content[0].text,
                                name=function_name,
                                item_id=current_item_id,
                                output_index=current_output_index,
                                sequence_number=-1,
                                call_id=saved_tool_call_id or f"call_{random_uuid()}",
                                status="completed",
                            )
                            if logger.isEnabledFor(logging.DEBUG):
                                try:
                                    logger.debug(
                                        "TOOL_CALL done: response=%s call_id=%s name=%s args_len=%d",
                                        request.request_id,
                                        function_call_item.call_id,
                                        function_call_item.name,
                                        len(function_call_item.arguments or ""),
                                    )
                                except Exception:
                                    pass
                            yield _increment_sequence_number_and_return(
                                ResponseOutputItemDoneEvent(
                                    type="response.output_item.done",
                                    sequence_number=-1,
                                    output_index=current_output_index,
                                    item=function_call_item,
                                )
                            )
                            # Mark stream closed for this call to avoid
                            # duplicate compat finishers later in the loop.
                            if session is not None and function_call_item.call_id:
                                st = session.pending_tool_calls.get(function_call_item.call_id)
                                if st is not None:
                                    st.stream_closed = True
                    elif previous_item.channel == "analysis":
                        content = ResponseReasoningTextContent(
                            text=previous_item.content[0].text,
                            type="reasoning_text",
                        )
                        reasoning_item = ResponseReasoningItem(
                            type="reasoning",
                            content=[content],
                            status="completed",
                            id=current_item_id,
                            summary=[],
                        )
                        for event in self._build_reasoning_done_events(
                            response_id=request.request_id,
                            reasoning_text=previous_item.content[0].text,
                            item_id=current_item_id,
                            output_index=current_output_index,
                            content_index=current_content_index,
                        ):
                            yield _increment_sequence_number_and_return(event)
                        for summary_event in self._generate_reasoning_summary_events(
                            response_id=request.request_id,
                            reasoning_text=previous_item.content[0].text,
                            item_id=current_item_id,
                            output_index=current_output_index,
                        ):
                            yield _increment_sequence_number_and_return(
                                summary_event
                            )
                        for context_event in self._generate_additional_context_events(
                            request,
                            response_id=request.request_id,
                            reasoning_text=previous_item.content[0].text,
                        ):
                            yield _increment_sequence_number_and_return(
                                context_event
                            )
                        yield _increment_sequence_number_and_return(
                            ResponseReasoningPartDoneEvent(
                                type="response.reasoning_part.done",
                                sequence_number=-1,
                                item_id=current_item_id,
                                output_index=current_output_index,
                                content_index=current_content_index,
                                part=content,
                            )
                        )
                        yield _increment_sequence_number_and_return(
                            ResponseOutputItemDoneEvent(
                                type="response.output_item.done",
                                sequence_number=-1,
                                output_index=current_output_index,
                                item=reasoning_item,
                            )
                        )
                    elif previous_item.channel == "final":
                        text_content = ResponseOutputText(
                            type="output_text",
                            text=previous_item.content[0].text,
                            annotations=[],
                        )
                        yield _increment_sequence_number_and_return(
                            ResponseTextDoneEvent(
                                type="response.output_text.done",
                                sequence_number=-1,
                                output_index=current_output_index,
                                content_index=current_content_index,
                                text=previous_item.content[0].text,
                                logprobs=[],
                                item_id=current_item_id,
                            )
                        )
                        yield _increment_sequence_number_and_return(
                            ResponseContentPartDoneEvent(
                                type="response.content_part.done",
                                sequence_number=-1,
                                item_id=current_item_id,
                                output_index=current_output_index,
                                content_index=current_content_index,
                                part=text_content,
                            )
                        )
                        yield _increment_sequence_number_and_return(
                            ResponseOutputItemDoneEvent(
                                type="response.output_item.done",
                                sequence_number=-1,
                                output_index=current_output_index,
                                item=ResponseOutputMessage(
                                    id=current_item_id,
                                    type="message",
                                    role="assistant",
                                    content=[text_content],
                                    status="completed",
                                ),
                            )
                        )

            # stream the output of a harmony message
            if ctx.parser.last_content_delta:
                if (
                    ctx.parser.current_channel == "final"
                    and ctx.parser.current_recipient is None
                ):
                    if not sent_output_item_added:
                        sent_output_item_added = True
                        current_item_id = f"msg_{random_uuid()}"
                        yield _increment_sequence_number_and_return(
                            ResponseOutputItemAddedEvent(
                                type="response.output_item.added",
                                sequence_number=-1,
                                output_index=current_output_index,
                                item=ResponseOutputMessage(
                                    id=current_item_id,
                                    type="message",
                                    role="assistant",
                                    content=[],
                                    status="in_progress",
                                ),
                            )
                        )
                        current_content_index += 1
                        yield _increment_sequence_number_and_return(
                            ResponseContentPartAddedEvent(
                                type="response.content_part.added",
                                sequence_number=-1,
                                output_index=current_output_index,
                                item_id=current_item_id,
                                content_index=current_content_index,
                                part=ResponseOutputText(
                                    type="output_text",
                                    text="",
                                    annotations=[],
                                    logprobs=[],
                                ),
                            )
                        )
                    yield _increment_sequence_number_and_return(
                        ResponseTextDeltaEvent(
                            type="response.output_text.delta",
                            sequence_number=-1,
                            content_index=current_content_index,
                            output_index=current_output_index,
                            item_id=current_item_id,
                            delta=ctx.parser.last_content_delta,
                            # TODO, use logprobs from ctx.last_request_output
                            logprobs=[],
                        )
                    )
                elif (
                    ctx.parser.current_channel == "analysis"
                    and ctx.parser.current_recipient is None
                ):
                    if not sent_output_item_added:
                        sent_output_item_added = True
                        current_item_id = f"msg_{random_uuid()}"
                        yield _increment_sequence_number_and_return(
                            ResponseOutputItemAddedEvent(
                                type="response.output_item.added",
                                sequence_number=-1,
                                output_index=current_output_index,
                                item=ResponseReasoningItem(
                                    type="reasoning",
                                    id=current_item_id,
                                    summary=[],
                                    status="in_progress",
                                ),
                            )
                        )
                        current_content_index += 1
                        yield _increment_sequence_number_and_return(
                            ResponseReasoningPartAddedEvent(
                                type="response.reasoning_part.added",
                                sequence_number=-1,
                                output_index=current_output_index,
                                item_id=current_item_id,
                                content_index=current_content_index,
                                part=ResponseReasoningTextContent(
                                    text="",
                                    type="reasoning_text",
                                ),
                            )
                        )
                    for event in self._build_reasoning_delta_events(
                        response_id=request.request_id,
                        delta_text=ctx.parser.last_content_delta,
                        item_id=current_item_id,
                        output_index=current_output_index,
                        content_index=current_content_index,
                    ):
                        yield _increment_sequence_number_and_return(event)
                # built-in tools will be triggered on the analysis channel
                # However, occasionally built-in tools will
                # still be output to commentary.
                elif (
                    ctx.parser.current_channel == "commentary"
                    or ctx.parser.current_channel == "analysis"
                ) and ctx.parser.current_recipient == "python":
                    if not sent_output_item_added:
                        sent_output_item_added = True
                        current_item_id = f"tool_{random_uuid()}"
                        yield _increment_sequence_number_and_return(
                            ResponseOutputItemAddedEvent(
                                type="response.output_item.added",
                                sequence_number=-1,
                                output_index=current_output_index,
                                item=ResponseCodeInterpreterToolCallParam(
                                    type="code_interpreter_call",
                                    id=current_item_id,
                                    code=None,
                                    container_id="auto",
                                    outputs=[],
                                    status="in_progress",
                                ),
                            )
                        )
                        yield _increment_sequence_number_and_return(
                            ResponseCodeInterpreterCallInProgressEvent(
                                type="response.code_interpreter_call.in_progress",
                                sequence_number=-1,
                                output_index=current_output_index,
                                item_id=current_item_id,
                            )
                        )
                    yield _increment_sequence_number_and_return(
                        ResponseCodeInterpreterCallCodeDeltaEvent(
                            type="response.code_interpreter_call_code.delta",
                            sequence_number=-1,
                            output_index=current_output_index,
                            item_id=current_item_id,
                            delta=ctx.parser.last_content_delta,
                        )
                    )

            # stream tool call outputs
            if ctx.is_assistant_action_turn() and len(ctx.parser.messages) > 0:
                previous_item = ctx.parser.messages[-1]
                if (
                    self.tool_server is not None
                    and self.tool_server.has_tool("browser")
                    and previous_item.recipient is not None
                    and previous_item.recipient.startswith("browser.")
                ):
                    function_name = previous_item.recipient[len("browser.") :]
                    action = None
                    parsed_args = self._safe_json_loads(
                        previous_item.content[0].text,
                        tool_name=function_name,
                    )
                    if parsed_args is None:
                        continue
                    if function_name == "search":
                        action = response_function_web_search.ActionSearch(
                            type="search",
                            query=parsed_args["query"],
                        )
                    elif function_name == "open":
                        action = response_function_web_search.ActionOpenPage(
                            type="open_page",
                            # TODO: translate to url
                            url=f"cursor:{parsed_args.get('cursor', '')}",
                        )
                    elif function_name == "find":
                        action = response_function_web_search.ActionFind(
                            type="find",
                            pattern=parsed_args["pattern"],
                            # TODO: translate to url
                            url=f"cursor:{parsed_args.get('cursor', '')}",
                        )
                    else:
                        raise ValueError(f"Unknown function name: {function_name}")

                    current_item_id = f"tool_{random_uuid()}"
                    yield _increment_sequence_number_and_return(
                        ResponseOutputItemAddedEvent(
                            type="response.output_item.added",
                            sequence_number=-1,
                            output_index=current_output_index,
                            item=response_function_web_search.ResponseFunctionWebSearch(
                                # TODO: generate a unique id for web search call
                                type="web_search_call",
                                id=current_item_id,
                                action=action,
                                status="in_progress",
                            ),
                        )
                    )
                    yield _increment_sequence_number_and_return(
                        ResponseWebSearchCallInProgressEvent(
                            type="response.web_search_call.in_progress",
                            sequence_number=-1,
                            output_index=current_output_index,
                            item_id=current_item_id,
                        )
                    )
                    yield _increment_sequence_number_and_return(
                        ResponseWebSearchCallSearchingEvent(
                            type="response.web_search_call.searching",
                            sequence_number=-1,
                            output_index=current_output_index,
                            item_id=current_item_id,
                        )
                    )

                    # enqueue
                    yield _increment_sequence_number_and_return(
                        ResponseWebSearchCallCompletedEvent(
                            type="response.web_search_call.completed",
                            sequence_number=-1,
                            output_index=current_output_index,
                            item_id=current_item_id,
                        )
                    )
                    yield _increment_sequence_number_and_return(
                        ResponseOutputItemDoneEvent(
                            type="response.output_item.done",
                            sequence_number=-1,
                            output_index=current_output_index,
                            item=ResponseFunctionWebSearch(
                                type="web_search_call",
                                id=current_item_id,
                                action=action,
                                status="completed",
                            ),
                        )
                    )
                    if include_file_search_results:
                        search_event = self._build_file_search_results_event(
                            request,
                            response_id=request.request_id,
                            item_id=current_item_id,
                            function_name=function_name,
                            parsed_args=parsed_args,
                        )
                        if search_event is not None:
                            yield _increment_sequence_number_and_return(search_event)
                    sources_event = self._build_web_search_sources_event(
                        request,
                        response_id=request.request_id,
                        item_id=current_item_id,
                        function_name=function_name,
                        parsed_args=parsed_args,
                    )
                    if sources_event is not None:
                        yield _increment_sequence_number_and_return(sources_event)
                elif (
                    previous_item.recipient is not None
                    and previous_item.recipient.startswith("file_search.")
                ):
                    parsed_args = self._safe_json_loads(
                        previous_item.content[0].text,
                        tool_name=previous_item.recipient,
                    )
                    current_item_id = f"tool_{random_uuid()}"
                    sent_output_item_added = True
                    yield _increment_sequence_number_and_return(
                        ResponseOutputItemAddedEvent(
                            type="response.output_item.added",
                            sequence_number=-1,
                            output_index=current_output_index,
                            item=ResponseFunctionToolCall(
                                id=current_item_id,
                                call_id=f"call_{random_uuid()}",
                                type="function_call",
                                status="in_progress",
                                name=previous_item.recipient,
                                arguments=previous_item.content[0].text,
                            ),
                        )
                    )
                    for event in self._build_file_search_call_events(
                        item_id=current_item_id,
                        output_index=current_output_index,
                    ):
                        yield _increment_sequence_number_and_return(event)
                    yield _increment_sequence_number_and_return(
                        ResponseOutputItemDoneEvent(
                            type="response.output_item.done",
                            sequence_number=-1,
                            output_index=current_output_index,
                            item=ResponseFunctionToolCall(
                                id=current_item_id,
                                call_id=f"call_{random_uuid()}",
                                type="function_call",
                                status="completed",
                                name=previous_item.recipient,
                                arguments=previous_item.content[0].text,
                            ),
                        )
                    )
                    if include_file_search_results and parsed_args is not None:
                        search_event = self._build_file_search_results_event(
                            request,
                            response_id=request.request_id,
                            item_id=current_item_id,
                            function_name=previous_item.recipient,
                            parsed_args=parsed_args,
                        )
                        if search_event is not None:
                            yield _increment_sequence_number_and_return(search_event)
                elif (
                    previous_item.recipient is not None
                    and (
                        previous_item.recipient.startswith("image_generation.")
                        or previous_item.recipient.startswith("images.")
                    )
                ):
                    self._require_image_tools_enabled(previous_item.recipient)
                    parsed_args = self._safe_json_loads(
                        previous_item.content[0].text,
                        tool_name=previous_item.recipient,
                    )
                    current_item_id = f"tool_{random_uuid()}"
                    sent_output_item_added = True
                    yield _increment_sequence_number_and_return(
                        ResponseOutputItemAddedEvent(
                            type="response.output_item.added",
                            sequence_number=-1,
                            output_index=current_output_index,
                            item=ResponseFunctionToolCall(
                                id=current_item_id,
                                call_id=f"call_{random_uuid()}",
                                type="function_call",
                                status="in_progress",
                                name=previous_item.recipient,
                                arguments=previous_item.content[0].text,
                            ),
                        )
                    )
                    partial_b64 = None
                    if isinstance(parsed_args, dict):
                        partial_b64 = parsed_args.get("partial_image_b64")
                    for event in self._build_image_generation_call_events(
                        item_id=current_item_id,
                        output_index=current_output_index,
                        partial_image_b64=partial_b64,
                    ):
                        yield _increment_sequence_number_and_return(event)
                    yield _increment_sequence_number_and_return(
                        ResponseOutputItemDoneEvent(
                            type="response.output_item.done",
                            sequence_number=-1,
                            output_index=current_output_index,
                            item=ResponseFunctionToolCall(
                                id=current_item_id,
                                call_id=f"call_{random_uuid()}",
                                type="function_call",
                                status="completed",
                                name=previous_item.recipient,
                                arguments=previous_item.content[0].text,
                            ),
                        )
                    )

                if (
                    self.tool_server is not None
                    and self.tool_server.has_tool("python")
                    and previous_item.recipient is not None
                    and previous_item.recipient.startswith("python")
                ):
                    yield _increment_sequence_number_and_return(
                        ResponseCodeInterpreterCallCodeDoneEvent(
                            type="response.code_interpreter_call_code.done",
                            sequence_number=-1,
                            output_index=current_output_index,
                            item_id=current_item_id,
                            code=previous_item.content[0].text,
                        )
                    )
                    yield _increment_sequence_number_and_return(
                        ResponseCodeInterpreterCallInterpretingEvent(
                            type="response.code_interpreter_call.interpreting",
                            sequence_number=-1,
                            output_index=current_output_index,
                            item_id=current_item_id,
                        )
                    )
                    yield _increment_sequence_number_and_return(
                        ResponseCodeInterpreterCallCompletedEvent(
                            type="response.code_interpreter_call.completed",
                            sequence_number=-1,
                            output_index=current_output_index,
                            item_id=current_item_id,
                        )
                    )
                    outputs_payload = None
                    if (
                        include_code_outputs
                        and previous_item.content
                        and previous_item.content[0].text
                    ):
                        outputs_payload = [
                            {
                                "type": "output_text",
                                "text": previous_item.content[0].text,
                            }
                        ]
                    yield _increment_sequence_number_and_return(
                        ResponseOutputItemDoneEvent(
                            type="response.output_item.done",
                            sequence_number=-1,
                            output_index=current_output_index,
                            item=ResponseCodeInterpreterToolCallParam(
                                type="code_interpreter_call",
                                id=current_item_id,
                                code=previous_item.content[0].text,
                                container_id="auto",
                                outputs=outputs_payload or [],
                                status="completed",
                            ),
                        )
                    )
            # developer tools will be triggered on the commentary channel
            # and recipient starts with "functions.TOOL_NAME"
            if (
                ctx.parser.current_channel == "commentary"
                and ctx.parser.current_recipient
                and ctx.parser.current_recipient.startswith("functions.")
            ):
                delta_text = ctx.parser.last_content_delta or ""
                if is_first_function_call_delta is False:
                    is_first_function_call_delta = True
                    fc_name = ctx.parser.current_recipient[len("functions.") :]
                    current_tool_call_name = fc_name
                    current_tool_call_id = f"call_{random_uuid()}"
                    current_tool_arguments = ""
                    current_item_id = f"fc_{random_uuid()}"
                    tool_call_item = ResponseFunctionToolCall(
                        name=fc_name,
                        type="function_call",
                        id=current_item_id,
                        call_id=current_tool_call_id,
                        arguments="",
                        status="in_progress",
                    )
                    if session is not None:
                        session.register_tool_call(current_item_id, tool_call_item)
                    if logger.isEnabledFor(logging.DEBUG):
                        try:
                            logger.debug(
                                "TOOL_CALL added: response=%s item_id=%s call_id=%s name=%s",
                                request.request_id,
                                current_item_id,
                                current_tool_call_id,
                                fc_name,
                            )
                        except Exception:
                            pass
                    yield _increment_sequence_number_and_return(
                        ResponseOutputItemAddedEvent(
                            type="response.output_item.added",
                            sequence_number=-1,
                            output_index=current_output_index,
                            item=tool_call_item,
                        )
                    )
                if delta_text:
                    tool_call_id_for_event: str | None = None
                    tool_name_for_event: str | None = None
                    arguments_text = delta_text
                    if session is not None:
                        session.append_tool_call_delta(current_item_id, delta_text)
                        tool_call_id_for_event = session.tool_calls_by_item_id.get(
                            current_item_id
                        )
                        if tool_call_id_for_event is not None:
                            pending_state = session.pending_tool_calls.get(
                                tool_call_id_for_event
                            )
                            if pending_state is not None:
                                tool_name_for_event = pending_state.tool_call.name
                                arguments_text = pending_state.tool_call.arguments or ""
                    else:
                        tool_call_id_for_event = current_tool_call_id
                        tool_name_for_event = current_tool_call_name
                        current_tool_arguments += delta_text
                        arguments_text = current_tool_arguments
                    # In compatibility mode, skip the extra tool_call.delta surface noise.
                    if (
                        tool_call_id_for_event is not None
                        and not self.compatibility_mode
                    ):
                        yield _increment_sequence_number_and_return(
                            self._build_tool_call_delta_event(
                                response_id=request.request_id,
                                tool_call_id=tool_call_id_for_event,
                                tool_name=tool_name_for_event,
                                arguments_text=arguments_text,
                            )
                        )
                    yield _increment_sequence_number_and_return(
                        ResponseFunctionCallArgumentsDeltaEvent(
                            item_id=current_item_id,
                            delta=delta_text,
                            output_index=current_output_index,
                            sequence_number=-1,
                            type="response.function_call_arguments.delta",
                        )
                    )

    async def responses_stream_generator(
        self,
        request: ResponsesRequest,
        sampling_params: SamplingParams,
        result_generator: AsyncIterator[ConversationContext | None],
        context: ConversationContext,
        model_name: str,
        tokenizer: AnyTokenizer,
        request_metadata: RequestResponseMetadata,
        created_time: int | None = None,
        session: ResponseStreamSession | None = None,
    ) -> AsyncGenerator[StreamingResponsesResponse, None]:
        # TODO:
        # 1. Handle disconnect

        created_time = created_time or int(time.time())

        # (moved below after sequence-number helper is defined)

        user_id = request.user or "anonymous"
        rate_limiter = self.rate_limiter

        sequence_number = 0

        def _increment_sequence_number_and_return(
            event: StreamingResponsesResponse,
        ) -> StreamingResponsesResponse:
            nonlocal sequence_number
            # Set sequence_number if the event has this attribute
            if hasattr(event, "sequence_number"):
                event.sequence_number = sequence_number
            sequence_number += 1
            return event

        # If this request continues a previous response and includes tool
        # outputs (Codex posts a new /v1/responses turn after executing the
        # tool locally), emit finisher events for any tool calls that were
        # left in_progress in the previous turn so that the model can resume.
        # This mirrors: response.tool_call.completed → response.output_item.done
        # before we proceed with new generation.
        prev_response_id = request.previous_response_id
        if prev_response_id:
            try:
                prev_response = await self._get_stored_response(prev_response_id)
            except Exception:
                prev_response = None
            if prev_response is not None:
                # Walk previous output items and finalize any function_call
                # items that remained in_progress.
                for prev_item in getattr(prev_response, "output", []) or []:
                    try:
                        # ResponseFunctionToolCall from previous turn that was
                        # left in_progress (i.e., a tool call awaiting output).
                        if (
                            isinstance(prev_item, ResponseFunctionToolCall)
                            and prev_item.status == "in_progress"
                        ):
                            call_id = prev_item.call_id
                            if call_id:
                                if logger.isEnabledFor(logging.DEBUG):
                                    try:
                                        logger.debug(
                                            "TOOL_CALL finalize prev: response=%s prev_response=%s call_id=%s",
                                            request.request_id,
                                            prev_response_id,
                                            call_id,
                                        )
                                    except Exception:
                                        pass
                                yield _increment_sequence_number_and_return(
                                    ResponseToolCallCompletedEvent(
                                        type="response.tool_call.completed",
                                        response={"id": request.request_id},
                                        call_id=call_id,
                                        sequence_number=-1,
                                    )
                                )
                            # Emit output_item.done to close the function_call item
                            done_item = ResponseFunctionToolCall(
                                id=prev_item.id,
                                call_id=prev_item.call_id,
                                type="function_call",
                                status="completed",
                                name=prev_item.name,
                                arguments=prev_item.arguments or "",
                            )
                            if logger.isEnabledFor(logging.DEBUG):
                                try:
                                    logger.debug(
                                        "TOOL_CALL done prev: response=%s call_id=%s name=%s args_len=%d",
                                        request.request_id,
                                        done_item.call_id,
                                        done_item.name,
                                        len(done_item.arguments or ""),
                                    )
                                except Exception:
                                    pass
                            yield _increment_sequence_number_and_return(
                                ResponseOutputItemDoneEvent(
                                    type="response.output_item.done",
                                    sequence_number=-1,
                                    output_index=0,
                                    item=done_item,
                                )
                            )
                    except Exception:
                        logger.exception(
                            "Failed to emit finisher events for previous tool call in %s",
                            prev_response_id,
                        )

        # Echo client-provided tool call items from request.input as SSE
        # so downstream clients and the model receive a consistent stream
        # (important for UIs and agents that open/close tool gates based on SSE).
        # IMPORTANT: In compatibility mode (Codex), do NOT echo tool calls from input.
        # Codex sends the entire history in request.input (user messages + old tool calls + tool outputs).
        # Echoing them would duplicate tool calls in the SSE stream.
        if not self.compatibility_mode and isinstance(request.input, list):
            for input_item in request.input:
                try:
                    if isinstance(input_item, ResponseFunctionToolCall):
                        # Always reflect the added event
                        if logger.isEnabledFor(logging.DEBUG):
                            try:
                                logger.debug(
                                    "TOOL_CALL added echo: response=%s item_id=%s call_id=%s name=%s",
                                    request.request_id,
                                    input_item.id,
                                    input_item.call_id,
                                    input_item.name,
                                )
                            except Exception:
                                pass
                        yield _increment_sequence_number_and_return(
                            ResponseOutputItemAddedEvent(
                                type="response.output_item.added",
                                sequence_number=-1,
                                output_index=0,
                                item=input_item,
                            )
                        )
                        # If client marked the call as completed, emit done
                        if (input_item.status or "").lower() == "completed":
                            if logger.isEnabledFor(logging.DEBUG):
                                try:
                                    logger.debug(
                                        "TOOL_CALL done echo: response=%s call_id=%s name=%s args_len=%d",
                                        request.request_id,
                                        input_item.call_id,
                                        input_item.name,
                                        len(input_item.arguments or ""),
                                    )
                                except Exception:
                                    pass
                            yield _increment_sequence_number_and_return(
                                ResponseOutputItemDoneEvent(
                                    type="response.output_item.done",
                                    sequence_number=-1,
                                    output_index=0,
                                    item=input_item,
                                )
                            )
                except Exception:
                    logger.exception("Failed to echo tool call input item as SSE")

        async with AsyncExitStack() as exit_stack:
            processer = None
            if self.use_harmony:
                # TODO: in streaming, we noticed this bug:
                # https://github.com/vllm-project/vllm/issues/25697
                await self._initialize_tool_sessions(request, context, exit_stack)
                processer = self._process_harmony_streaming_events
            else:
                processer = self._process_simple_streaming_events
            # TODO Hanchen make sampling params to include the structural tag

            image_event = self._build_message_input_image_event(request)
            if image_event is not None:
                yield _increment_sequence_number_and_return(image_event)

            queued_response = ResponsesResponse.from_request(
                request,
                sampling_params,
                model_name=model_name,
                created_time=created_time,
                output=[],
                status="queued",
                usage=None,
            ).model_dump()
            yield _increment_sequence_number_and_return(
                ResponseQueuedEvent(
                    type="response.queued",
                    sequence_number=-1,
                    response=queued_response,
                )
            )
            initial_response = ResponsesResponse.from_request(
                request,
                sampling_params,
                model_name=model_name,
                created_time=created_time,
                output=[],
                status="in_progress",
                usage=None,
            ).model_dump()
            yield _increment_sequence_number_and_return(
                ResponseCreatedEvent(
                    type="response.created",
                    sequence_number=-1,
                    response=initial_response,
                )
            )
            yield _increment_sequence_number_and_return(
                ResponseInProgressEvent(
                    type="response.in_progress",
                    sequence_number=-1,
                    response=initial_response,
                )
            )

            if self._should_emit_computer_call_placeholder(request):
                placeholder_event = self._build_context_event(
                    response_id=request.request_id,
                    payload={
                        "computer_call_output.output.image_url": None,
                    },
                )
                yield _increment_sequence_number_and_return(placeholder_event)

            current_generator = result_generator
            while True:
                async for event_data in processer(
                    request,
                    sampling_params,
                    current_generator,
                    context,
                    model_name,
                    tokenizer,
                    request_metadata,
                    created_time,
                    _increment_sequence_number_and_return,
                    session=session,
                ):
                    yield event_data

                if session is not None and session.has_pending_tool_calls():
                    # Emit completion markers for any open tool calls so
                    # clients can act on them even if they don't POST
                    # /tool_outputs.
                    if session.pending_tool_calls:
                        for call_id, state in list(session.pending_tool_calls.items()):
                            # Skip calls already closed in the stream.
                            if getattr(state, "stream_closed", False):
                                continue
                            # 1) response.tool_call.completed
                            if logger.isEnabledFor(logging.DEBUG):
                                try:
                                    logger.debug(
                                        "TOOL_CALL completed (compat): response=%s call_id=%s",
                                        request.request_id,
                                        call_id,
                                    )
                                except Exception:
                                    pass
                            yield _increment_sequence_number_and_return(
                                ResponseToolCallCompletedEvent(
                                    type="response.tool_call.completed",
                                    response={"id": request.request_id},
                                    call_id=call_id,
                                    sequence_number=-1,
                                )
                            )
                            # 2) response.output_item.done (function_call)
                            try:
                                done_item = ResponseFunctionToolCall(
                                    id=state.tool_call.id,
                                    call_id=state.tool_call.call_id,
                                    type="function_call",
                                    status="completed",
                                    name=state.tool_call.name,
                                    arguments=state.tool_call.arguments or "",
                                )
                                if logger.isEnabledFor(logging.DEBUG):
                                    try:
                                        logger.debug(
                                            "TOOL_CALL done (compat): response=%s call_id=%s name=%s args_len=%d",
                                            request.request_id,
                                            done_item.call_id,
                                            done_item.name,
                                            len(done_item.arguments or ""),
                                        )
                                    except Exception:
                                        pass
                                yield _increment_sequence_number_and_return(
                                    ResponseOutputItemDoneEvent(
                                        type="response.output_item.done",
                                        sequence_number=-1,
                                        output_index=0,
                                        item=done_item,
                                    )
                                )
                                state.stream_closed = True
                            except Exception:
                                logger.exception("Failed to emit output_item.done for tool call %s", call_id)

                    # In compatibility mode (Codex), close the stream after tool call.
                    # Codex will execute the tool locally and POST new /v1/responses with previous_response_id.
                    # The server will continue the SAME response (not create a new one).
                    if self.compatibility_mode:
                        logger.debug(
                            "Response %s (compatibility mode): tool calls done, closing stream. "
                            "Expecting client to POST new /v1/responses with previous_response_id",
                            request.request_id
                        )
                        break

                    # Standard mode: wait for POST /v1/responses/{id}/tool_outputs in the same stream
                    logger.debug(
                        "Response %s has pending tool calls, waiting for tool outputs...",
                        request.request_id
                    )
                    current_generator = await self._await_tool_outputs(session)
                    continue
                break

            async def empty_async_generator():
                # A hack to trick Python to think this is a generator but
                # in fact it immediately returns.
                if False:
                    yield

            final_response = await self.responses_full_generator(
                request,
                sampling_params,
                empty_async_generator(),
                context,
                model_name,
                tokenizer,
                request_metadata,
                created_time=created_time,
            )
            assert isinstance(final_response, ResponsesResponse)
            if final_response.status == "incomplete":
                terminal_event: StreamingResponsesResponse = ResponseIncompleteEvent(
                    type="response.incomplete",
                    sequence_number=-1,
                    response=final_response,
                )
            else:
                terminal_event = ResponseCompletedEvent(
                    type="response.completed",
                    sequence_number=-1,
                    response=final_response,
                )
            yield _increment_sequence_number_and_return(terminal_event)
            if rate_limiter is not None:
                usage = final_response.usage
                total_tokens = usage.total_tokens if usage is not None else 0
                await rate_limiter.record_tokens(user_id, total_tokens)
                limits_payload = await rate_limiter.build_rate_limit_payload(user_id)
                yield _increment_sequence_number_and_return(
                    ResponseRateLimitsUpdatedEvent(
                        type="response.rate_limits.updated",
                        response={"id": final_response.id},
                        limits=limits_payload,
                        sequence_number=-1,
                    )
                )
    def _cleanup_response_store_locked(self) -> None:
        now = time.monotonic()
        if self.response_store_ttl > 0:
            expired = [
                resp_id
                for resp_id, ts in self.response_store_expirations.items()
                if now - ts >= self.response_store_ttl
            ]
            for resp_id in expired:
                self._evict_response_locked(resp_id)
        if len(self.response_store) > self.response_store_max_entries:
            sorted_items = sorted(
                self.response_store_expirations.items(), key=lambda item: item[1]
            )
            for resp_id, _ in sorted_items:
                if len(self.response_store) <= self.response_store_max_entries:
                    break
                self._evict_response_locked(resp_id)
        if self.response_store_max_bytes is not None:
            sorted_items = sorted(
                self.response_store_expirations.items(), key=lambda item: item[1]
            )
            for resp_id, _ in sorted_items:
                if (
                    self.response_store_total_bytes
                    <= self.response_store_max_bytes
                ):
                    break
                self._evict_response_locked(resp_id)

    def _evict_response_locked(self, response_id: str) -> None:
        response_removed = self.response_store.pop(response_id, None)
        self.response_store_expirations.pop(response_id, None)
        size = self.response_store_sizes.pop(response_id, 0)
        self.response_input_items.pop(response_id, None)
        if response_removed is not None:
            self.response_store_total_bytes = max(
                0, self.response_store_total_bytes - size
            )

    async def _store_response_object(self, response: ResponsesResponse) -> None:
        if not self.enable_store:
            return
        async with self.response_store_lock:
            self._cleanup_response_store_locked()
            now = time.monotonic()
            prev_size = self.response_store_sizes.get(response.id, 0)
            self.response_store_total_bytes = max(
                0, self.response_store_total_bytes - prev_size
            )
            self.response_store[response.id] = response
            self.response_store_expirations[response.id] = now
            size = len(response.model_dump_json().encode("utf-8"))
            self.response_store_sizes[response.id] = size
            self.response_store_total_bytes += size
            self._cleanup_response_store_locked()

    async def _set_or_update_stored_response(
        self, response: ResponsesResponse
    ) -> None:
        if not self.enable_store:
            return
        async with self.response_store_lock:
            self._cleanup_response_store_locked()
            stored = self.response_store.get(response.id)
            if stored is not None and stored.status == "cancelled":
                return
            prev_size = self.response_store_sizes.get(response.id, 0)
            self.response_store_total_bytes = max(
                0, self.response_store_total_bytes - prev_size
            )
            self.response_store[response.id] = response
            now = time.monotonic()
            self.response_store_expirations[response.id] = now
            size = len(response.model_dump_json().encode("utf-8"))
            self.response_store_sizes[response.id] = size
            self.response_store_total_bytes += size
            self._cleanup_response_store_locked()

    async def _get_stored_response(self, response_id: str) -> ResponsesResponse | None:
        async with self.response_store_lock:
            self._cleanup_response_store_locked()
            return self.response_store.get(response_id)

    async def _update_stored_response_status(
        self, response_id: str, status: ResponseStatus | str
    ) -> None:
        if not self.enable_store:
            return
        async with self.response_store_lock:
            self._cleanup_response_store_locked()
            stored = self.response_store.get(response_id)
            if stored is not None and stored.status not in ("completed", "cancelled"):
                stored.status = status
                self.response_store_expirations[response_id] = time.monotonic()
    def _maybe_check_request_id(
        self,
        header_request_id: str | None,
        request: ResponsesRequest,
    ) -> ErrorResponse | None:
        if not header_request_id:
            return None
        if header_request_id != request.request_id:
            return self.create_error_response(
                err_type="invalid_request_error",
                message=(
                    "Request ID mismatch: header X-Request-Id "
                    f"{header_request_id!r} != body request_id "
                    f"{request.request_id!r}."
                ),
                status_code=HTTPStatus.BAD_REQUEST,
            )
        return None
