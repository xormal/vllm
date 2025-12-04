# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project
import asyncio
import hashlib
import importlib
import inspect
import json
import logging
import math
import time
import multiprocessing
import multiprocessing.forkserver as forkserver
import os
import secrets
import signal
import socket
import tempfile
import uuid
from argparse import Namespace
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from http import HTTPStatus
from typing import Annotated, Any, Final, Literal

import model_hosting_container_standards.sagemaker as sagemaker_standards
import prometheus_client
import pydantic
import regex as re
import uvloop
from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from prometheus_client import make_asgi_app
from prometheus_fastapi_instrumentator import Instrumentator
from starlette.concurrency import iterate_in_threadpool
from starlette.datastructures import URL, Headers, MutableHeaders, State
from starlette.routing import Mount
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from typing_extensions import assert_never

import vllm.envs as envs
from vllm.config import VllmConfig
from vllm.engine.arg_utils import AsyncEngineArgs
from vllm.engine.protocol import EngineClient
from vllm.entrypoints.anthropic.protocol import (
    AnthropicError,
    AnthropicErrorResponse,
    AnthropicMessagesRequest,
    AnthropicMessagesResponse,
)
from vllm.entrypoints.anthropic.serving_messages import AnthropicServingMessages
from vllm.entrypoints.launcher import serve_http
from vllm.entrypoints.logger import RequestLogger
from vllm.entrypoints.openai.cli_args import make_arg_parser, validate_parsed_serve_args
from vllm.entrypoints.openai.orca_metrics import metrics_header
from vllm.entrypoints.openai.protocol import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ClassificationRequest,
    ClassificationResponse,
    CompletionRequest,
    CompletionResponse,
    DetokenizeRequest,
    DetokenizeResponse,
    EmbeddingBytesResponse,
    EmbeddingRequest,
    EmbeddingResponse,
    ErrorInfo,
    ErrorResponse,
    GenerateRequest,
    GenerateResponse,
    IOProcessorResponse,
    PoolingBytesResponse,
    PoolingRequest,
    PoolingResponse,
    RerankRequest,
    RerankResponse,
    ResponsesRequest,
    ResponsesToolOutputsRequest,
    ResponsesResponse,
    ResponseErrorEvent,
    ResponsePingEvent,
    ConversationCreateRequest,
    ConversationListItemsResponse,
    ConversationUpdateRequest,
    ConversationItemsCreateRequest,
    ScoreRequest,
    ScoreResponse,
    StreamingResponsesResponse,
    TokenizeRequest,
    TokenizeResponse,
    TranscriptionRequest,
    TranscriptionResponse,
    TranslationRequest,
    TranslationResponse,
)
from vllm.entrypoints.openai.serving_chat import OpenAIServingChat
from vllm.entrypoints.openai.serving_classification import ServingClassification
from vllm.entrypoints.openai.serving_completion import OpenAIServingCompletion
from vllm.entrypoints.openai.serving_embedding import OpenAIServingEmbedding
from vllm.entrypoints.openai.serving_engine import OpenAIServing
from vllm.entrypoints.openai.serving_models import (
    BaseModelPath,
    OpenAIServingModels,
)
from vllm.entrypoints.openai.serving_pooling import OpenAIServingPooling
from vllm.entrypoints.openai.serving_responses import OpenAIServingResponses
from vllm.entrypoints.openai.serving_score import ServingScores
from vllm.entrypoints.openai.serving_tokenization import OpenAIServingTokenization
from vllm.entrypoints.openai.serving_tokens import ServingTokens
from vllm.entrypoints.openai.serving_transcription import (
    OpenAIServingTranscription,
    OpenAIServingTranslation,
)
from vllm.entrypoints.openai.tool_parsers import ToolParserManager
from vllm.entrypoints.tool_server import DemoToolServer, MCPToolServer, ToolServer
from vllm.entrypoints.utils import (
    cli_env_setup,
    load_aware_call,
    log_non_default_args,
    process_chat_template,
    process_lora_modules,
    with_cancellation,
)
from vllm.logger import init_logger
from vllm.reasoning import ReasoningParserManager
from vllm.entrypoints.openai.conversation_store import (
    ConversationStore,
    ConversationNotFoundError,
)
from vllm.tasks import POOLING_TASKS
from vllm.usage.usage_lib import UsageContext
from vllm.utils.argparse_utils import FlexibleArgumentParser
from vllm.utils.gc_utils import freeze_gc_heap
from vllm.utils.network_utils import is_valid_ipv6_address
from vllm.utils.system_utils import decorate_logs, set_ulimit
from vllm.v1.engine.exceptions import EngineDeadError
from vllm.v1.metrics.prometheus import get_prometheus_registry
from vllm.version import __version__ as VLLM_VERSION

prometheus_multiproc_dir: tempfile.TemporaryDirectory

# Cannot use __name__ (https://github.com/vllm-project/vllm/pull/4765)
logger = init_logger("vllm.entrypoints.openai.api_server")

ENDPOINT_LOAD_METRICS_FORMAT_HEADER_LABEL = "endpoint-load-metrics-format"
SUPPORTED_AZURE_API_VERSIONS = [
    "2024-02-15-preview",
    "2024-03-01-preview",
    "2024-05-01-preview",
]

_running_tasks: set[asyncio.Task] = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        if app.state.log_stats:
            engine_client: EngineClient = app.state.engine_client

            async def _force_log():
                while True:
                    await asyncio.sleep(envs.VLLM_LOG_STATS_INTERVAL)
                    await engine_client.do_log_stats()

            task = asyncio.create_task(_force_log())
            _running_tasks.add(task)
            task.add_done_callback(_running_tasks.remove)
        else:
            task = None

        # Mark the startup heap as static so that it's ignored by GC.
        # Reduces pause times of oldest generation collections.
        freeze_gc_heap()
        try:
            yield
        finally:
            if task is not None:
                task.cancel()
    finally:
        # Ensure app state including engine ref is gc'd
        del app.state


@asynccontextmanager
async def build_async_engine_client(
    args: Namespace,
    *,
    usage_context: UsageContext = UsageContext.OPENAI_API_SERVER,
    disable_frontend_multiprocessing: bool | None = None,
    client_config: dict[str, Any] | None = None,
) -> AsyncIterator[EngineClient]:
    if os.getenv("VLLM_WORKER_MULTIPROC_METHOD") == "forkserver":
        # The executor is expected to be mp.
        # Pre-import heavy modules in the forkserver process
        logger.debug("Setup forkserver with pre-imports")
        multiprocessing.set_start_method("forkserver")
        multiprocessing.set_forkserver_preload(["vllm.v1.engine.async_llm"])
        forkserver.ensure_running()
        logger.debug("Forkserver setup complete!")

    # Context manager to handle engine_client lifecycle
    # Ensures everything is shutdown and cleaned up on error/exit
    engine_args = AsyncEngineArgs.from_cli_args(args)
    if client_config:
        engine_args._api_process_count = client_config.get("client_count", 1)
        engine_args._api_process_rank = client_config.get("client_index", 0)

    if disable_frontend_multiprocessing is None:
        disable_frontend_multiprocessing = bool(args.disable_frontend_multiprocessing)

    async with build_async_engine_client_from_engine_args(
        engine_args,
        usage_context=usage_context,
        disable_frontend_multiprocessing=disable_frontend_multiprocessing,
        client_config=client_config,
    ) as engine:
        yield engine


@asynccontextmanager
async def build_async_engine_client_from_engine_args(
    engine_args: AsyncEngineArgs,
    *,
    usage_context: UsageContext = UsageContext.OPENAI_API_SERVER,
    disable_frontend_multiprocessing: bool = False,
    client_config: dict[str, Any] | None = None,
) -> AsyncIterator[EngineClient]:
    """
    Create EngineClient, either:
        - in-process using the AsyncLLMEngine Directly
        - multiprocess using AsyncLLMEngine RPC

    Returns the Client or None if the creation failed.
    """

    # Create the EngineConfig (determines if we can use V1).
    vllm_config = engine_args.create_engine_config(usage_context=usage_context)

    if disable_frontend_multiprocessing:
        logger.warning("V1 is enabled, but got --disable-frontend-multiprocessing.")

    from vllm.v1.engine.async_llm import AsyncLLM

    async_llm: AsyncLLM | None = None

    # Don't mutate the input client_config
    client_config = dict(client_config) if client_config else {}
    client_count = client_config.pop("client_count", 1)
    client_index = client_config.pop("client_index", 0)

    try:
        async_llm = AsyncLLM.from_vllm_config(
            vllm_config=vllm_config,
            usage_context=usage_context,
            enable_log_requests=engine_args.enable_log_requests,
            aggregate_engine_logging=engine_args.aggregate_engine_logging,
            disable_log_stats=engine_args.disable_log_stats,
            client_addresses=client_config,
            client_count=client_count,
            client_index=client_index,
        )

        # Don't keep the dummy data in memory
        assert async_llm is not None
        await async_llm.reset_mm_cache()

        yield async_llm
    finally:
        if async_llm:
            async_llm.shutdown()


async def validate_json_request(raw_request: Request):
    content_type = raw_request.headers.get("content-type", "").lower()
    media_type = content_type.split(";", maxsplit=1)[0]
    if media_type != "application/json":
        raise RequestValidationError(
            errors=["Unsupported Media Type: Only 'application/json' is allowed"]
        )


router = APIRouter()


class PrometheusResponse(Response):
    media_type = prometheus_client.CONTENT_TYPE_LATEST


def mount_metrics(app: FastAPI):
    """Mount prometheus metrics to a FastAPI app."""

    registry = get_prometheus_registry()

    # `response_class=PrometheusResponse` is needed to return an HTTP response
    # with header "Content-Type: text/plain; version=0.0.4; charset=utf-8"
    # instead of the default "application/json" which is incorrect.
    # See https://github.com/trallnag/prometheus-fastapi-instrumentator/issues/163#issue-1296092364
    Instrumentator(
        excluded_handlers=[
            "/metrics",
            "/health",
            "/load",
            "/ping",
            "/version",
            "/server_info",
        ],
        registry=registry,
    ).add().instrument(app).expose(app, response_class=PrometheusResponse)

    # Add prometheus asgi middleware to route /metrics requests
    metrics_route = Mount("/metrics", make_asgi_app(registry=registry))

    # Workaround for 307 Redirect for /metrics
    metrics_route.path_regex = re.compile("^/metrics(?P<path>.*)$")
    app.routes.append(metrics_route)


def base(request: Request) -> OpenAIServing:
    # Reuse the existing instance
    return tokenization(request)


def models(request: Request) -> OpenAIServingModels:
    return request.app.state.openai_serving_models


def responses(request: Request) -> OpenAIServingResponses | None:
    return request.app.state.openai_serving_responses


def conversations_store(request: Request) -> ConversationStore | None:
    return getattr(request.app.state, "conversation_store", None)


def messages(request: Request) -> AnthropicServingMessages:
    return request.app.state.anthropic_serving_messages


def chat(request: Request) -> OpenAIServingChat | None:
    return request.app.state.openai_serving_chat


def completion(request: Request) -> OpenAIServingCompletion | None:
    return request.app.state.openai_serving_completion


def pooling(request: Request) -> OpenAIServingPooling | None:
    return request.app.state.openai_serving_pooling


def embedding(request: Request) -> OpenAIServingEmbedding | None:
    return request.app.state.openai_serving_embedding


def score(request: Request) -> ServingScores | None:
    return request.app.state.openai_serving_scores


def classify(request: Request) -> ServingClassification | None:
    return request.app.state.openai_serving_classification


def rerank(request: Request) -> ServingScores | None:
    return request.app.state.openai_serving_scores


def tokenization(request: Request) -> OpenAIServingTokenization:
    return request.app.state.openai_serving_tokenization


def transcription(request: Request) -> OpenAIServingTranscription:
    return request.app.state.openai_serving_transcription


def translation(request: Request) -> OpenAIServingTranslation:
    return request.app.state.openai_serving_translation


def engine_client(request: Request) -> EngineClient:
    return request.app.state.engine_client


def generate_tokens(request: Request) -> ServingTokens | None:
    return request.app.state.serving_tokens


@router.get("/health", response_class=Response)
async def health(raw_request: Request) -> Response:
    """Health check."""
    try:
        await engine_client(raw_request).check_health()
        return Response(status_code=200)
    except EngineDeadError:
        return Response(status_code=503)


@router.get("/load")
async def get_server_load_metrics(request: Request):
    # This endpoint returns the current server load metrics.
    # It tracks requests utilizing the GPU from the following routes:
    # - /v1/chat/completions
    # - /v1/completions
    # - /v1/audio/transcriptions
    # - /v1/audio/translations
    # - /v1/embeddings
    # - /pooling
    # - /classify
    # - /score
    # - /v1/score
    # - /rerank
    # - /v1/rerank
    # - /v2/rerank
    return JSONResponse(content={"server_load": request.app.state.server_load_metrics})


@router.post("/pause")
async def pause_generation(
    raw_request: Request,
    wait_for_inflight_requests: bool = Query(False),
    clear_cache: bool = Query(True),
) -> JSONResponse:
    """Pause generation requests to allow weight updates.

    Args:
        wait_for_inflight_requests: When ``True`` waits for in-flight
            requests to finish before pausing. When ``False`` (default),
            aborts any in-flight requests immediately.
        clear_cache: Whether to clear KV/prefix caches after draining.
    """

    engine = engine_client(raw_request)

    try:
        await engine.pause_generation(
            wait_for_inflight_requests=wait_for_inflight_requests,
            clear_cache=clear_cache,
        )
        return JSONResponse(
            content={"status": "paused"},
            status_code=HTTPStatus.OK.value,
        )

    except ValueError as err:
        return JSONResponse(
            content={"error": str(err)},
            status_code=HTTPStatus.BAD_REQUEST.value,
        )
    except Exception as err:  # pragma: no cover - defensive
        logger.exception("Failed to pause generation")
        return JSONResponse(
            content={"error": f"Failed to pause generation: {err}"},
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR.value,
        )


@router.post("/resume")
async def resume_generation(raw_request: Request) -> JSONResponse:
    """Resume generation after a pause."""

    engine = engine_client(raw_request)

    try:
        await engine.resume_generation()
        return JSONResponse(
            content={"status": "resumed"},
            status_code=HTTPStatus.OK.value,
        )
    except Exception as err:  # pragma: no cover - defensive
        logger.exception("Failed to resume generation")
        return JSONResponse(
            content={"error": f"Failed to resume generation: {err}"},
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR.value,
        )


@router.get("/is_paused")
async def is_paused(raw_request: Request) -> JSONResponse:
    """Return the current pause status."""

    engine = engine_client(raw_request)

    try:
        paused = await engine.is_paused()
    except Exception as err:  # pragma: no cover - defensive
        logger.exception("Failed to fetch pause status")
        return JSONResponse(
            content={"error": f"Failed to fetch pause status: {err}"},
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR.value,
        )

    return JSONResponse(content={"is_paused": paused})


@router.post(
    "/tokenize",
    dependencies=[Depends(validate_json_request)],
    responses={
        HTTPStatus.BAD_REQUEST.value: {"model": ErrorResponse},
        HTTPStatus.NOT_FOUND.value: {"model": ErrorResponse},
        HTTPStatus.INTERNAL_SERVER_ERROR.value: {"model": ErrorResponse},
        HTTPStatus.NOT_IMPLEMENTED.value: {"model": ErrorResponse},
    },
)
@with_cancellation
async def tokenize(request: TokenizeRequest, raw_request: Request):
    handler = tokenization(raw_request)

    try:
        generator = await handler.create_tokenize(request, raw_request)
    except NotImplementedError as e:
        raise HTTPException(
            status_code=HTTPStatus.NOT_IMPLEMENTED.value, detail=str(e)
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR.value, detail=str(e)
        ) from e

    if isinstance(generator, ErrorResponse):
        return JSONResponse(
            content=generator.model_dump(), status_code=generator.error.code
        )
    elif isinstance(generator, TokenizeResponse):
        return JSONResponse(content=generator.model_dump())

    assert_never(generator)


@router.post(
    "/detokenize",
    dependencies=[Depends(validate_json_request)],
    responses={
        HTTPStatus.BAD_REQUEST.value: {"model": ErrorResponse},
        HTTPStatus.NOT_FOUND.value: {"model": ErrorResponse},
        HTTPStatus.INTERNAL_SERVER_ERROR.value: {"model": ErrorResponse},
    },
)
@with_cancellation
async def detokenize(request: DetokenizeRequest, raw_request: Request):
    handler = tokenization(raw_request)

    try:
        generator = await handler.create_detokenize(request, raw_request)
    except OverflowError as e:
        raise RequestValidationError(errors=[str(e)]) from e
    except Exception as e:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR.value, detail=str(e)
        ) from e

    if isinstance(generator, ErrorResponse):
        return JSONResponse(
            content=generator.model_dump(), status_code=generator.error.code
        )
    elif isinstance(generator, DetokenizeResponse):
        return JSONResponse(content=generator.model_dump())

    assert_never(generator)


def maybe_register_tokenizer_info_endpoint(args):
    """Conditionally register the tokenizer info endpoint if enabled."""
    if getattr(args, "enable_tokenizer_info_endpoint", False):

        @router.get("/tokenizer_info")
        async def get_tokenizer_info(raw_request: Request):
            """Get comprehensive tokenizer information."""
            result = await tokenization(raw_request).get_tokenizer_info()
            return JSONResponse(
                content=result.model_dump(),
                status_code=result.error.code
                if isinstance(result, ErrorResponse)
                else 200,
            )


@router.get("/v1/models")
async def show_available_models(raw_request: Request):
    handler = models(raw_request)

    models_ = await handler.show_available_models()
    return JSONResponse(content=models_.model_dump())


@router.get("/version")
async def show_version():
    ver = {"version": VLLM_VERSION}
    return JSONResponse(content=ver)


class SSEValidationError(Exception):
    """Raised when a streaming payload cannot be serialized as SSE."""


class SSEEventValidator:
    """Validates outgoing SSE events to prevent malformed streams."""

    _ALLOWED_EVENT_TYPES: Final[set[str]] = {
        "response.created",
        "response.in_progress",
        "response.queued",
        "response.completed",
        "response.tool_call.delta",
        "response.output_item.added",
        "response.output_item.done",
        "response.content_part.added",
        "response.content_part.done",
        "response.output_text.delta",
        "response.output_text.done",
        "response.function_call_arguments.delta",
        "response.function_call_arguments.done",
        "response.incomplete",
        "response.reasoning.delta",
        "response.reasoning.done",
        "response.reasoning.summary.delta",
        "response.reasoning.summary.added",
        "response.reasoning_summary_text.delta",
        "response.reasoning_summary_text.done",
        "response.reasoning_summary_part.added",
        "response.reasoning_summary_part.done",
        "response.additional_context",
        "response.rate_limits.updated",
        "response.error",
        "response.reasoning_text.delta",
        "response.reasoning_text.done",
        "response.reasoning_part.added",
        "response.reasoning_part.done",
        "response.code_interpreter_call.in_progress",
        "response.code_interpreter_call_code.delta",
        "response.code_interpreter_call_code.done",
        "response.code_interpreter_call.interpreting",
        "response.code_interpreter_call.completed",
        "response.web_search_call.in_progress",
        "response.web_search_call.searching",
        "response.web_search_call.completed",
        "response.file_search_call.in_progress",
        "response.file_search_call.searching",
        "response.file_search_call.completed",
        "response.image_generation_call.in_progress",
        "response.image_generation_call.generating",
        "response.image_generation_call.completed",
        "response.image_generation_call.partial_image",
        "response.ping",
        "response.tool_call.completed",
    }

    _EVENT_TYPE_PATTERN = re.compile(r"^response(\.[a-z0-9_]+)+$")

    def validate(self, event_type: str, event_dict: dict[str, Any]) -> None:
        if not event_type:
            raise SSEValidationError("Missing SSE event type.")
        if "\n" in event_type or "\r" in event_type:
            raise SSEValidationError("SSE event type must not contain newlines.")
        if not self._EVENT_TYPE_PATTERN.match(event_type):
            raise SSEValidationError(f"Invalid SSE event format: {event_type!r}")
        if event_type not in self._ALLOWED_EVENT_TYPES:
            raise SSEValidationError(f"Unsupported SSE event: {event_type}")
        sequence_number = event_dict.get("sequence_number")
        if not isinstance(sequence_number, int) or sequence_number < 0:
            raise SSEValidationError("sequence_number must be a non-negative integer.")

    def build_validation_error_event(
        self,
        *,
        original_event: dict[str, Any],
        message: str,
    ) -> dict[str, Any]:
        response_meta = original_event.get("response") or {}
        response_id = response_meta.get("id")
        payload = {
            "type": "response.error",
            "response": {"status": "failed"},
            "error": {
                "message": message,
                "type": "stream_validation_error",
                "code": HTTPStatus.INTERNAL_SERVER_ERROR.value,
            },
            "sequence_number": max(
                0, int(original_event.get("sequence_number", 0))
            ),
        }
        if response_id:
            payload["response"]["id"] = response_id
        return payload


class SSEChunkBuffer:
    """Aggregates SSE chunks to reduce write amplification."""

    def __init__(self, max_bytes: int = 16_384) -> None:
        self.max_bytes = max(1024, max_bytes)
        self._buffer: list[str] = []
        self._size = 0

    def append(self, chunk: str) -> list[str]:
        self._buffer.append(chunk)
        self._size += len(chunk.encode("utf-8"))
        if self._size >= self.max_bytes:
            return self.flush()
        return []

    def flush(self) -> list[str]:
        if not self._buffer:
            return []
        combined = "".join(self._buffer)
        self._buffer.clear()
        self._size = 0
        return [combined]


SSE_EVENT_VALIDATOR = SSEEventValidator()


def _format_sse_chunk(event_type: str, payload: Mapping[str, Any]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"


async def _convert_stream_to_sse_events(
    generator: AsyncGenerator[StreamingResponsesResponse, None],
    *,
    on_disconnect: Callable[[], Awaitable[None]] | None = None,
    ping_interval: float = 0.0,
    compatibility_mode: bool = False,
) -> AsyncGenerator[str, None]:
    """Convert the generator to a stream of events in SSE format"""
    try:
        sequence_validator = SSE_EVENT_VALIDATOR
        chunk_buffer = SSEChunkBuffer()
        sequence_number = 0
        last_heartbeat = time.monotonic()
        async for event in generator:
            now = time.monotonic()
            if ping_interval > 0 and (now - last_heartbeat) >= ping_interval:
                for chunk in chunk_buffer.flush():
                    yield chunk
                ping_event = ResponsePingEvent(
                    type="response.ping",
                    response={},
                    sequence_number=sequence_number,
                    timestamp=now,
                )
                yield _format_sse_chunk(
                    ping_event.type,
                    ping_event.model_dump(),
                )
                last_heartbeat = now
            event_dict = event.model_dump(exclude_none=True)
            event_dict.setdefault("type", getattr(event, "type", ""))
            if compatibility_mode:
                _apply_compatibility_shims(event_dict)
            seq = event_dict.get("sequence_number")
            if not isinstance(seq, int) or seq < sequence_number:
                seq = sequence_number
                event_dict["sequence_number"] = seq
            sequence_number = seq + 1
            event_type = str(event_dict.get("type") or "")
            try:
                sequence_validator.validate(event_type, event_dict)
            except SSEValidationError as exc:
                logger.error(
                    "Invalid SSE event (%s): %s",
                    event_type or "<missing>",
                    exc,
                )
                for chunk in chunk_buffer.flush():
                    yield chunk
                error_event = sequence_validator.build_validation_error_event(
                    original_event=event_dict,
                    message=str(exc),
                )
                yield _format_sse_chunk(error_event["type"], error_event)
                return
            chunk = _format_sse_chunk(event_type, event_dict)
            for buffered in chunk_buffer.append(chunk):
                yield buffered
            last_heartbeat = now
        for chunk in chunk_buffer.flush():
            yield chunk
        # For Responses API in compatibility mode (Codex), do not emit
        # the Chat Completions-style terminator. Clients rely on
        # response.completed as the terminal event and treat "[DONE]"
        # as a non-JSON payload that pollutes logs.
        if not compatibility_mode:
            yield "data: [DONE]\n\n"
    except asyncio.CancelledError:
        if on_disconnect is not None:
            try:
                await on_disconnect()
            except Exception:
                logger.exception(
                    "Failed to cleanup streaming session after disconnect."
                )
        raise


def _build_stream_disconnect_handler(
    handler: OpenAIServingResponses | None,
    response_id: str | None,
) -> Callable[[], Awaitable[None]] | None:
    if handler is None or not response_id:
        return None

    async def _cleanup():
        await handler.handle_stream_disconnect(
            response_id,
            reason="client_disconnect",
        )

    return _cleanup


_DEFAULT_RETRY_AFTER_SECONDS = 1.0


def _maybe_add_retry_after_header(
    response: Response,
    error: ErrorResponse,
    retry_after: float | None = None,
) -> None:
    if error.error.code != HTTPStatus.TOO_MANY_REQUESTS.value:
        return
    seconds = (
        retry_after
        if retry_after is not None
        else (error.retry_after if error.retry_after is not None else None)
    )
    if seconds is None:
        seconds = _DEFAULT_RETRY_AFTER_SECONDS
    seconds = max(0.0, float(seconds))
    response.headers.setdefault("Retry-After", str(max(1, math.ceil(seconds))))


def _json_error_response(error: ErrorResponse) -> JSONResponse:
    response = JSONResponse(
        content=error.model_dump(),
        status_code=error.error.code,
    )
    _maybe_add_retry_after_header(response, error)
    return response


def _finalize_responses_result(
    generator: ResponsesResponse
    | ErrorResponse
    | AsyncGenerator[StreamingResponsesResponse, None],
    *,
    stream: bool,
    request_id: str,
    handler: OpenAIServingResponses | None = None,
) -> Response:
    if isinstance(generator, ErrorResponse):
        if stream:
            return _stream_error_response(generator, request_id=request_id)
        return _json_error_response(generator)
    if isinstance(generator, ResponsesResponse):
        return JSONResponse(content=generator.model_dump())
    disconnect_handler = _build_stream_disconnect_handler(handler, request_id)
    ping_interval = handler.ping_interval_seconds if handler else 0.0
    return StreamingResponse(
        content=_convert_stream_to_sse_events(
            generator,
            on_disconnect=disconnect_handler,
            ping_interval=ping_interval,
            compatibility_mode=getattr(handler, "compatibility_mode", False),
        ),
        media_type="text/event-stream",
    )


async def _apply_standard_response_headers(
    response: Response,
    handler: OpenAIServingResponses | None,
    *,
    raw_request: Request | None,
    request_id: str | None,
    user_id: str | None,
) -> None:
    if handler is None:
        return
    headers = raw_request.headers if raw_request is not None else Headers({})
    if request_id:
        response.headers.setdefault("x-request-id", request_id)
    org_value = headers.get("OpenAI-Organization")
    if not org_value:
        org_value = handler.default_openai_organization
    if org_value:
        response.headers.setdefault("OpenAI-Organization", org_value)
    version_value = headers.get("OpenAI-Version")
    if not version_value:
        version_value = handler.default_openai_version
    if version_value:
        response.headers.setdefault("OpenAI-Version", version_value)
    user = user_id or "anonymous"
    rate_headers = await handler.build_rate_limit_headers(user)
    for key, value in rate_headers.items():
        response.headers.setdefault(key, value)


def _stream_error_response(
    error_response: ErrorResponse,
    *,
    request_id: str | None,
) -> StreamingResponse:
    response_payload: dict[str, Any] = {"status": "failed"}
    if request_id:
        response_payload["id"] = request_id
    event = ResponseErrorEvent(
        response=response_payload,
        error=error_response.error,
        sequence_number=0,
    )

    async def generator():
        yield f"event: {event.type}\n"
        yield f"data: {event.model_dump_json()}\n\n"

    response = StreamingResponse(generator(), media_type="text/event-stream")
    _maybe_add_retry_after_header(response, error_response)
    return response

@router.post(
    "/v1/responses",
    dependencies=[Depends(validate_json_request)],
    responses={
        HTTPStatus.OK.value: {"content": {"text/event-stream": {}}},
        HTTPStatus.BAD_REQUEST.value: {"model": ErrorResponse},
        HTTPStatus.NOT_FOUND.value: {"model": ErrorResponse},
        HTTPStatus.INTERNAL_SERVER_ERROR.value: {"model": ErrorResponse},
    },
)
@with_cancellation
async def create_responses(request: ResponsesRequest, raw_request: Request):
    handler = responses(raw_request)
    if handler is None:
        return _json_error_response(
            base(raw_request).create_error_response(
                message="The model does not support Responses API"
            )
        )
    if isinstance(request.input, list):
        request.input = _attach_item_ids(request.input)
    try:
        generator = await handler.create_responses(request, raw_request)
    except Exception as e:
        # Log full traceback for debugging
        logger.exception("Exception in create_responses handler:")
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR.value, detail=str(e)
        ) from e

    response = _finalize_responses_result(
        generator,
        stream=bool(request.stream),
        request_id=request.request_id,
        handler=handler,
    )
    await _apply_standard_response_headers(
        response,
        handler,
        raw_request=raw_request,
        request_id=request.request_id,
        user_id=request.user,
    )
    return response


@router.post(
    "/v1/responses/compact",
    dependencies=[Depends(validate_json_request)],
    responses={
        HTTPStatus.OK.value: {"content": {"text/event-stream": {}}},
        HTTPStatus.BAD_REQUEST.value: {"model": ErrorResponse},
        HTTPStatus.NOT_FOUND.value: {"model": ErrorResponse},
        HTTPStatus.INTERNAL_SERVER_ERROR.value: {"model": ErrorResponse},
    },
)
@with_cancellation
async def create_responses_compact(
    request: ResponsesRequest,
    raw_request: Request,
):
    if not request.instructions:
        request.instructions = "Summarize conversation history to reduce context size."
    return await create_responses(request, raw_request)


@router.post(
    "/v1/responses/tokenize",
    dependencies=[Depends(validate_json_request)],
    responses={
        HTTPStatus.OK.value: {"model": ResponsesResponse},
        HTTPStatus.BAD_REQUEST.value: {"model": ErrorResponse},
        HTTPStatus.NOT_FOUND.value: {"model": ErrorResponse},
        HTTPStatus.INTERNAL_SERVER_ERROR.value: {"model": ErrorResponse},
    },
)
@with_cancellation
async def tokenize_responses(
    request: ResponsesRequest,
    raw_request: Request,
):
    handler = responses(raw_request)
    if handler is None:
        return _json_error_response(
            base(raw_request).create_error_response(
                message="The model does not support Responses API"
            )
        )
    if isinstance(request.input, list):
        request.input = _attach_item_ids(request.input)
    request.stream = False
    try:
        result = await handler.tokenize_responses(request, raw_request)
    except Exception as exc:
        logger.exception("Exception in tokenize_responses handler:")
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR.value, detail=str(exc)
        ) from exc

    response = _finalize_responses_result(
        result,
        stream=False,
        request_id=request.request_id,
        handler=handler,
    )
    await _apply_standard_response_headers(
        response,
        handler,
        raw_request=raw_request,
        request_id=request.request_id,
        user_id=request.user,
    )
    return response


def _attach_item_ids(items: list[Any]) -> list[Any]:
    attached: list[Any] = []
    for index, item in enumerate(items):
        new_id = f"item_{index}_{uuid.uuid4().hex}"
        if isinstance(item, dict):
            item.setdefault("id", new_id)
            attached.append(item)
            continue
        if hasattr(item, "id") and getattr(item, "id", None) in (None, ""):
            try:
                setattr(item, "id", new_id)
            except Exception:
                pass
        attached.append(item)
    return attached


def _conversation_error_response(
    message: str,
    *,
    status_code: HTTPStatus = HTTPStatus.BAD_REQUEST,
) -> JSONResponse:
    return _json_error_response(
        ErrorResponse(
            error=ErrorInfo(
                message=message,
                type="invalid_request_error",
                code=status_code.value,
            )
        )
    )


async def _azure_auth_dependency(
    raw_request: Request,
    api_key: str | None = Header(default=None, alias="api-key"),
    authorization: str | None = Header(default=None),
):
    if not getattr(raw_request.app.state, "azure_api_enabled", False):
        return ""
    if api_key:
        if len(api_key) < 32:
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED.value,
                detail={
                    "error": {
                        "message": "Invalid API key format",
                        "type": "invalid_api_key",
                        "code": HTTPStatus.UNAUTHORIZED.value,
                    }
                },
            )
        return api_key
    if authorization and authorization.startswith("Bearer "):
        return authorization
    raise HTTPException(
        status_code=HTTPStatus.UNAUTHORIZED.value,
        detail={
            "error": {
                "message": (
                    "Authentication required. Provide api-key or Authorization token."
                ),
                "type": "authentication_error",
                "code": HTTPStatus.UNAUTHORIZED.value,
            }
        },
    )


@router.post(
    "/openai/deployments/{deployment_name}/responses",
    dependencies=[Depends(validate_json_request)],
    responses={
        HTTPStatus.OK.value: {"content": {"text/event-stream": {}}},
        HTTPStatus.BAD_REQUEST.value: {"model": ErrorResponse},
        HTTPStatus.NOT_FOUND.value: {"model": ErrorResponse},
        HTTPStatus.UNAUTHORIZED.value: {"model": ErrorResponse},
    },
)
@with_cancellation
async def create_responses_azure(
    deployment_name: str,
    request: ResponsesRequest,
    raw_request: Request,
    api_version: str = Query(default="2024-02-15-preview", alias="api-version"),
    _credentials: str = Depends(_azure_auth_dependency),
):
    state = raw_request.app.state
    if not getattr(state, "azure_api_enabled", False):
        return _json_error_response(
            base(raw_request).create_error_response(
                err_type="invalid_request_error",
                message="Azure endpoint support is not enabled on this server.",
                status_code=HTTPStatus.NOT_FOUND,
            )
        )
    if api_version not in SUPPORTED_AZURE_API_VERSIONS:
        return JSONResponse(
            status_code=HTTPStatus.BAD_REQUEST.value,
            content={
                "error": {
                    "message": (
                        f"Unsupported api-version: {api_version}. "
                        f"Supported versions: {', '.join(SUPPORTED_AZURE_API_VERSIONS)}"
                    ),
                    "type": "invalid_request_error",
                    "code": HTTPStatus.BAD_REQUEST.value,
                }
            },
        )

    handler = responses(raw_request)
    if handler is None:
        return _json_error_response(
            base(raw_request).create_error_response(
                message="The model does not support Responses API"
            )
        )

    if not request.store:
        logger.warning_once("Azure requires store=true; overriding provided value.")
        request.store = True
    if not request.model:
        request.model = deployment_name
    if isinstance(request.input, list):
        request.input = _attach_item_ids(request.input)

    try:
        generator = await handler.create_responses(request, raw_request)
    except Exception as exc:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR.value, detail=str(exc)
        ) from exc

    response = _finalize_responses_result(
        generator,
        stream=bool(request.stream),
        request_id=request.request_id,
        handler=handler,
    )
    region = getattr(state, "azure_region", "eastus")
    response.headers.setdefault("x-ms-region", region)
    response.headers.setdefault("x-ms-request-id", request.request_id)
    response.headers.setdefault(
        "api-supported-versions", ",".join(SUPPORTED_AZURE_API_VERSIONS)
    )
    response.headers.setdefault("x-ms-api-version", api_version)
    await _apply_standard_response_headers(
        response,
        handler,
        raw_request=raw_request,
        request_id=request.request_id,
        user_id=request.user,
    )
    return response


@router.get("/v1/responses/{response_id}")
async def retrieve_responses(
    response_id: str,
    raw_request: Request,
    starting_after: int | None = None,
    stream: bool | None = False,
):
    handler = responses(raw_request)
    if handler is None:
        return _json_error_response(
            base(raw_request).create_error_response(
                message="The model does not support Responses API"
            )
        )

    try:
        response = await handler.retrieve_responses(
            response_id,
            starting_after=starting_after,
            stream=stream,
        )
    except Exception as e:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR.value, detail=str(e)
        ) from e

    if isinstance(response, ErrorResponse):
        resp = _json_error_response(response)
        await _apply_standard_response_headers(
            resp,
            handler,
            raw_request=raw_request,
            request_id=response_id,
            user_id=None,
        )
        return resp
    if isinstance(response, ResponsesResponse):
        resp = JSONResponse(content=response.model_dump())
        await _apply_standard_response_headers(
            resp,
            handler,
            raw_request=raw_request,
            request_id=response_id,
            user_id=response.user,
        )
        return resp
    disconnect_handler = _build_stream_disconnect_handler(handler, response_id)
    streaming_response = StreamingResponse(
        content=_convert_stream_to_sse_events(
            response,
            on_disconnect=disconnect_handler,
        ),
        media_type="text/event-stream",
    )
    await _apply_standard_response_headers(
        streaming_response,
        handler,
        raw_request=raw_request,
        request_id=response_id,
        user_id=handler.get_session_user(response_id),
    )
    return streaming_response


@router.post("/v1/responses/{response_id}/cancel")
async def cancel_responses(response_id: str, raw_request: Request):
    handler = responses(raw_request)
    if handler is None:
        return _json_error_response(
            base(raw_request).create_error_response(
                message="The model does not support Responses API"
            )
        )

    try:
        response = await handler.cancel_responses(response_id)
    except Exception as e:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR.value, detail=str(e)
        ) from e

    if isinstance(response, ErrorResponse):
        resp = _json_error_response(response)
        await _apply_standard_response_headers(
            resp,
            handler,
            raw_request=raw_request,
            request_id=response_id,
            user_id=None,
        )
        return resp
    resp = JSONResponse(content=response.model_dump())
    await _apply_standard_response_headers(
        resp,
        handler,
        raw_request=raw_request,
        request_id=response_id,
        user_id=response.user,
    )
    return resp


@router.get("/v1/responses/{response_id}/input_items")
async def list_response_input_items(
    response_id: str,
    raw_request: Request,
    after: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    order: Literal["asc", "desc"] | str = Query(default="desc"),
    include: list[str] | None = Query(default=None),
):
    handler = responses(raw_request)
    if handler is None:
        return _json_error_response(
            base(raw_request).create_error_response(
                message="The model does not support Responses API"
            )
        )

    try:
        result = await handler.list_response_input_items(
            response_id,
            after=after,
            limit=limit,
            order=order,
            include=include,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR.value, detail=str(exc)
        ) from exc

    if isinstance(result, ErrorResponse):
        resp = _json_error_response(result)
        await _apply_standard_response_headers(
            resp,
            handler,
            raw_request=raw_request,
            request_id=response_id,
            user_id=None,
        )
        return resp
    response_payload, user_id = result
    resp = JSONResponse(content=response_payload)
    await _apply_standard_response_headers(
        resp,
        handler,
        raw_request=raw_request,
        request_id=response_id,
        user_id=user_id,
    )
    return resp


@router.post("/v1/responses/{response_id}/tool_outputs")
async def submit_tool_outputs(
    response_id: str,
    payload: ResponsesToolOutputsRequest,
    raw_request: Request,
):
    logger.debug(
        "Received tool outputs for response %s: tool_call_id=%s",
        response_id,
        payload.tool_call_id,
    )
    handler = responses(raw_request)
    if handler is None:
        return _json_error_response(
            base(raw_request).create_error_response(
                message="The model does not support Responses API"
            )
        )

    try:
        result = await handler.submit_tool_outputs(response_id, payload)
        logger.debug(
            "Tool outputs processed for response %s: status=%s",
            response_id,
            result.get("status") if isinstance(result, dict) else "unknown",
        )
    except Exception as e:
        logger.exception("Failed to submit tool outputs for response %s", response_id)
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR.value, detail=str(e)
        ) from e

    if isinstance(result, ErrorResponse):
        resp = _json_error_response(result)
        await _apply_standard_response_headers(
            resp,
            handler,
            raw_request=raw_request,
            request_id=response_id,
            user_id=handler.get_session_user(response_id),
        )
        return resp
    resp = JSONResponse(content=result)
    await _apply_standard_response_headers(
        resp,
        handler,
        raw_request=raw_request,
        request_id=response_id,
        user_id=handler.get_session_user(response_id),
    )
    return resp


@router.post("/v1/conversations")
async def create_conversation(
    payload: ConversationCreateRequest,
    raw_request: Request,
):
    store = conversations_store(raw_request)
    if store is None:
        return _conversation_error_response(
            "Conversations API is not enabled.", status_code=HTTPStatus.NOT_FOUND
        )
    conversation = await store.create_conversation(payload)
    return JSONResponse(content=conversation.model_dump())


@router.get("/v1/conversations/{conversation_id}")
async def retrieve_conversation(conversation_id: str, raw_request: Request):
    store = conversations_store(raw_request)
    if store is None:
        return _conversation_error_response(
            "Conversations API is not enabled.", status_code=HTTPStatus.NOT_FOUND
        )
    try:
        conversation = await store.get_conversation(conversation_id)
    except ConversationNotFoundError:
        return _conversation_error_response(
            f"Conversation '{conversation_id}' not found.",
            status_code=HTTPStatus.NOT_FOUND,
        )
    return JSONResponse(content=conversation.model_dump())


@router.post("/v1/conversations/{conversation_id}")
async def update_conversation(
    conversation_id: str,
    payload: ConversationUpdateRequest,
    raw_request: Request,
):
    store = conversations_store(raw_request)
    if store is None:
        return _conversation_error_response(
            "Conversations API is not enabled.", status_code=HTTPStatus.NOT_FOUND
        )
    try:
        conversation = await store.update_conversation(conversation_id, payload)
    except ConversationNotFoundError:
        return _conversation_error_response(
            f"Conversation '{conversation_id}' not found.",
            status_code=HTTPStatus.NOT_FOUND,
        )
    return JSONResponse(content=conversation.model_dump())


@router.delete("/v1/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, raw_request: Request):
    store = conversations_store(raw_request)
    if store is None:
        return _conversation_error_response(
            "Conversations API is not enabled.", status_code=HTTPStatus.NOT_FOUND
        )
    removed = await store.delete_conversation(conversation_id)
    if not removed:
        return _conversation_error_response(
            f"Conversation '{conversation_id}' not found.",
            status_code=HTTPStatus.NOT_FOUND,
        )
    return Response(status_code=HTTPStatus.NO_CONTENT.value)


@router.get("/v1/conversations/{conversation_id}/items")
async def list_conversation_items(
    conversation_id: str,
    raw_request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    order: Literal["asc", "desc"] = Query(default="desc"),
    after: str | None = Query(default=None),
):
    store = conversations_store(raw_request)
    if store is None:
        return _conversation_error_response(
            "Conversations API is not enabled.", status_code=HTTPStatus.NOT_FOUND
        )
    try:
        response = await store.list_items(
            conversation_id,
            limit=limit,
            order=order,
            after=after,
        )
    except ConversationNotFoundError as exc:
        return _conversation_error_response(
            f"Conversation item '{exc.args[0]}' not found.",
            status_code=HTTPStatus.NOT_FOUND,
        )
    except ValueError as exc:
        return _conversation_error_response(str(exc))
    return JSONResponse(content=response.model_dump())


@router.post("/v1/conversations/{conversation_id}/items")
async def create_conversation_items(
    conversation_id: str,
    payload: ConversationItemsCreateRequest,
    raw_request: Request,
):
    store = conversations_store(raw_request)
    if store is None:
        return _conversation_error_response(
            "Conversations API is not enabled.", status_code=HTTPStatus.NOT_FOUND
        )
    try:
        items = await store.create_items(conversation_id, payload)
    except ConversationNotFoundError:
        return _conversation_error_response(
            f"Conversation '{conversation_id}' not found.",
            status_code=HTTPStatus.NOT_FOUND,
        )
    return JSONResponse(
        content=ConversationListItemsResponse(
            data=items,
            has_more=False,
            first_id=items[0].id if items else None,
            last_id=items[-1].id if items else None,
        ).model_dump()
    )


@router.get("/v1/conversations/{conversation_id}/items/{item_id}")
async def get_conversation_item(
    conversation_id: str,
    item_id: str,
    raw_request: Request,
):
    store = conversations_store(raw_request)
    if store is None:
        return _conversation_error_response(
            "Conversations API is not enabled.", status_code=HTTPStatus.NOT_FOUND
        )
    try:
        item = await store.get_item(conversation_id, item_id)
    except ConversationNotFoundError:
        return _conversation_error_response(
            f"Conversation item '{item_id}' not found.",
            status_code=HTTPStatus.NOT_FOUND,
        )
    return JSONResponse(content=item.model_dump())


@router.delete("/v1/conversations/{conversation_id}/items/{item_id}")
async def delete_conversation_item(
    conversation_id: str,
    item_id: str,
    raw_request: Request,
):
    store = conversations_store(raw_request)
    if store is None:
        return _conversation_error_response(
            "Conversations API is not enabled.", status_code=HTTPStatus.NOT_FOUND
        )
    try:
        removed = await store.delete_item(conversation_id, item_id)
    except ConversationNotFoundError:
        return _conversation_error_response(
            f"Conversation '{conversation_id}' not found.",
            status_code=HTTPStatus.NOT_FOUND,
        )
    if not removed:
        return _conversation_error_response(
            f"Conversation item '{item_id}' not found.",
            status_code=HTTPStatus.NOT_FOUND,
        )
    return Response(status_code=HTTPStatus.NO_CONTENT.value)


@router.post(
    "/v1/messages",
    dependencies=[Depends(validate_json_request)],
    responses={
        HTTPStatus.OK.value: {"content": {"text/event-stream": {}}},
        HTTPStatus.BAD_REQUEST.value: {"model": AnthropicErrorResponse},
        HTTPStatus.NOT_FOUND.value: {"model": AnthropicErrorResponse},
        HTTPStatus.INTERNAL_SERVER_ERROR.value: {"model": AnthropicErrorResponse},
    },
)
@with_cancellation
@load_aware_call
async def create_messages(request: AnthropicMessagesRequest, raw_request: Request):
    def translate_error_response(response: ErrorResponse) -> JSONResponse:
        anthropic_error = AnthropicErrorResponse(
            error=AnthropicError(
                type=response.error.type,
                message=response.error.message,
            )
        )
        return JSONResponse(
            status_code=response.error.code, content=anthropic_error.model_dump()
        )

    handler = messages(raw_request)
    if handler is None:
        error = base(raw_request).create_error_response(
            message="The model does not support Messages API"
        )
        return translate_error_response(error)

    try:
        generator = await handler.create_messages(request, raw_request)
    except Exception as e:
        logger.exception("Error in create_messages: %s", e)
        return JSONResponse(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR.value,
            content=AnthropicErrorResponse(
                error=AnthropicError(
                    type="internal_error",
                    message=str(e),
                )
            ).model_dump(),
        )

    if isinstance(generator, ErrorResponse):
        return translate_error_response(generator)

    elif isinstance(generator, AnthropicMessagesResponse):
        resp = generator.model_dump(exclude_none=True)
        logger.debug("Anthropic Messages Response: %s", resp)
        return JSONResponse(content=resp)

    return StreamingResponse(content=generator, media_type="text/event-stream")


@router.post(
    "/v1/chat/completions",
    dependencies=[Depends(validate_json_request)],
    responses={
        HTTPStatus.OK.value: {"content": {"text/event-stream": {}}},
        HTTPStatus.BAD_REQUEST.value: {"model": ErrorResponse},
        HTTPStatus.NOT_FOUND.value: {"model": ErrorResponse},
        HTTPStatus.INTERNAL_SERVER_ERROR.value: {"model": ErrorResponse},
    },
)
@with_cancellation
@load_aware_call
async def create_chat_completion(request: ChatCompletionRequest, raw_request: Request):
    metrics_header_format = raw_request.headers.get(
        ENDPOINT_LOAD_METRICS_FORMAT_HEADER_LABEL, ""
    )
    handler = chat(raw_request)
    if handler is None:
        return base(raw_request).create_error_response(
            message="The model does not support Chat Completions API"
        )
    try:
        generator = await handler.create_chat_completion(request, raw_request)
    except Exception as e:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR.value, detail=str(e)
        ) from e
    if isinstance(generator, ErrorResponse):
        return JSONResponse(
            content=generator.model_dump(), status_code=generator.error.code
        )

    elif isinstance(generator, ChatCompletionResponse):
        return JSONResponse(
            content=generator.model_dump(),
            headers=metrics_header(metrics_header_format),
        )

    return StreamingResponse(content=generator, media_type="text/event-stream")


@router.post(
    "/v1/completions",
    dependencies=[Depends(validate_json_request)],
    responses={
        HTTPStatus.OK.value: {"content": {"text/event-stream": {}}},
        HTTPStatus.BAD_REQUEST.value: {"model": ErrorResponse},
        HTTPStatus.NOT_FOUND.value: {"model": ErrorResponse},
        HTTPStatus.INTERNAL_SERVER_ERROR.value: {"model": ErrorResponse},
    },
)
@with_cancellation
@load_aware_call
async def create_completion(request: CompletionRequest, raw_request: Request):
    metrics_header_format = raw_request.headers.get(
        ENDPOINT_LOAD_METRICS_FORMAT_HEADER_LABEL, ""
    )
    handler = completion(raw_request)
    if handler is None:
        return base(raw_request).create_error_response(
            message="The model does not support Completions API"
        )

    try:
        generator = await handler.create_completion(request, raw_request)
    except OverflowError as e:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST.value, detail=str(e)
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR.value, detail=str(e)
        ) from e

    if isinstance(generator, ErrorResponse):
        return JSONResponse(
            content=generator.model_dump(), status_code=generator.error.code
        )
    elif isinstance(generator, CompletionResponse):
        return JSONResponse(
            content=generator.model_dump(),
            headers=metrics_header(metrics_header_format),
        )

    return StreamingResponse(content=generator, media_type="text/event-stream")


@router.post(
    "/v1/embeddings",
    dependencies=[Depends(validate_json_request)],
    responses={
        HTTPStatus.BAD_REQUEST.value: {"model": ErrorResponse},
        HTTPStatus.INTERNAL_SERVER_ERROR.value: {"model": ErrorResponse},
    },
)
@with_cancellation
@load_aware_call
async def create_embedding(
    request: EmbeddingRequest,
    raw_request: Request,
):
    handler = embedding(raw_request)
    if handler is None:
        return base(raw_request).create_error_response(
            message="The model does not support Embeddings API"
        )

    try:
        generator = await handler.create_embedding(request, raw_request)
    except Exception as e:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR.value, detail=str(e)
        ) from e

    if isinstance(generator, ErrorResponse):
        return JSONResponse(
            content=generator.model_dump(), status_code=generator.error.code
        )
    elif isinstance(generator, EmbeddingResponse):
        return JSONResponse(content=generator.model_dump())
    elif isinstance(generator, EmbeddingBytesResponse):
        return StreamingResponse(
            content=generator.body,
            headers={"metadata": generator.metadata},
            media_type=generator.media_type,
        )

    assert_never(generator)


@router.post(
    "/pooling",
    dependencies=[Depends(validate_json_request)],
    responses={
        HTTPStatus.BAD_REQUEST.value: {"model": ErrorResponse},
        HTTPStatus.INTERNAL_SERVER_ERROR.value: {"model": ErrorResponse},
    },
)
@with_cancellation
@load_aware_call
async def create_pooling(request: PoolingRequest, raw_request: Request):
    handler = pooling(raw_request)
    if handler is None:
        return base(raw_request).create_error_response(
            message="The model does not support Pooling API"
        )
    try:
        generator = await handler.create_pooling(request, raw_request)
    except Exception as e:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR.value, detail=str(e)
        ) from e
    if isinstance(generator, ErrorResponse):
        return JSONResponse(
            content=generator.model_dump(), status_code=generator.error.code
        )
    elif isinstance(generator, (PoolingResponse, IOProcessorResponse)):
        return JSONResponse(content=generator.model_dump())
    elif isinstance(generator, PoolingBytesResponse):
        return StreamingResponse(
            content=generator.body,
            headers={"metadata": generator.metadata},
            media_type=generator.media_type,
        )

    assert_never(generator)


@router.post("/classify", dependencies=[Depends(validate_json_request)])
@with_cancellation
@load_aware_call
async def create_classify(request: ClassificationRequest, raw_request: Request):
    handler = classify(raw_request)
    if handler is None:
        return base(raw_request).create_error_response(
            message="The model does not support Classification API"
        )

    try:
        generator = await handler.create_classify(request, raw_request)
    except Exception as e:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR.value, detail=str(e)
        ) from e
    if isinstance(generator, ErrorResponse):
        return JSONResponse(
            content=generator.model_dump(), status_code=generator.error.code
        )

    elif isinstance(generator, ClassificationResponse):
        return JSONResponse(content=generator.model_dump())

    assert_never(generator)


@router.post(
    "/score",
    dependencies=[Depends(validate_json_request)],
    responses={
        HTTPStatus.BAD_REQUEST.value: {"model": ErrorResponse},
        HTTPStatus.INTERNAL_SERVER_ERROR.value: {"model": ErrorResponse},
    },
)
@with_cancellation
@load_aware_call
async def create_score(request: ScoreRequest, raw_request: Request):
    handler = score(raw_request)
    if handler is None:
        return base(raw_request).create_error_response(
            message="The model does not support Score API"
        )

    try:
        generator = await handler.create_score(request, raw_request)
    except Exception as e:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR.value, detail=str(e)
        ) from e
    if isinstance(generator, ErrorResponse):
        return JSONResponse(
            content=generator.model_dump(), status_code=generator.error.code
        )
    elif isinstance(generator, ScoreResponse):
        return JSONResponse(content=generator.model_dump())

    assert_never(generator)


@router.post(
    "/v1/score",
    dependencies=[Depends(validate_json_request)],
    responses={
        HTTPStatus.BAD_REQUEST.value: {"model": ErrorResponse},
        HTTPStatus.INTERNAL_SERVER_ERROR.value: {"model": ErrorResponse},
    },
)
@with_cancellation
@load_aware_call
async def create_score_v1(request: ScoreRequest, raw_request: Request):
    logger.warning(
        "To indicate that Score API is not part of standard OpenAI API, we "
        "have moved it to `/score`. Please update your client accordingly."
    )

    return await create_score(request, raw_request)


@router.post(
    "/v1/audio/transcriptions",
    responses={
        HTTPStatus.OK.value: {"content": {"text/event-stream": {}}},
        HTTPStatus.BAD_REQUEST.value: {"model": ErrorResponse},
        HTTPStatus.UNPROCESSABLE_ENTITY.value: {"model": ErrorResponse},
        HTTPStatus.INTERNAL_SERVER_ERROR.value: {"model": ErrorResponse},
    },
)
@with_cancellation
@load_aware_call
async def create_transcriptions(
    raw_request: Request, request: Annotated[TranscriptionRequest, Form()]
):
    handler = transcription(raw_request)
    if handler is None:
        return base(raw_request).create_error_response(
            message="The model does not support Transcriptions API"
        )

    audio_data = await request.file.read()
    try:
        generator = await handler.create_transcription(audio_data, request, raw_request)
    except Exception as e:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR.value, detail=str(e)
        ) from e

    if isinstance(generator, ErrorResponse):
        return JSONResponse(
            content=generator.model_dump(), status_code=generator.error.code
        )

    elif isinstance(generator, TranscriptionResponse):
        return JSONResponse(content=generator.model_dump())

    return StreamingResponse(content=generator, media_type="text/event-stream")


@router.post(
    "/v1/audio/translations",
    responses={
        HTTPStatus.OK.value: {"content": {"text/event-stream": {}}},
        HTTPStatus.BAD_REQUEST.value: {"model": ErrorResponse},
        HTTPStatus.UNPROCESSABLE_ENTITY.value: {"model": ErrorResponse},
        HTTPStatus.INTERNAL_SERVER_ERROR.value: {"model": ErrorResponse},
    },
)
@with_cancellation
@load_aware_call
async def create_translations(
    request: Annotated[TranslationRequest, Form()], raw_request: Request
):
    handler = translation(raw_request)
    if handler is None:
        return base(raw_request).create_error_response(
            message="The model does not support Translations API"
        )

    audio_data = await request.file.read()
    try:
        generator = await handler.create_translation(audio_data, request, raw_request)
    except Exception as e:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR.value, detail=str(e)
        ) from e

    if isinstance(generator, ErrorResponse):
        return JSONResponse(
            content=generator.model_dump(), status_code=generator.error.code
        )

    elif isinstance(generator, TranslationResponse):
        return JSONResponse(content=generator.model_dump())

    return StreamingResponse(content=generator, media_type="text/event-stream")


@router.post(
    "/rerank",
    dependencies=[Depends(validate_json_request)],
    responses={
        HTTPStatus.BAD_REQUEST.value: {"model": ErrorResponse},
        HTTPStatus.INTERNAL_SERVER_ERROR.value: {"model": ErrorResponse},
    },
)
@with_cancellation
@load_aware_call
async def do_rerank(request: RerankRequest, raw_request: Request):
    handler = rerank(raw_request)
    if handler is None:
        return base(raw_request).create_error_response(
            message="The model does not support Rerank (Score) API"
        )
    try:
        generator = await handler.do_rerank(request, raw_request)
    except Exception as e:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR.value, detail=str(e)
        ) from e
    if isinstance(generator, ErrorResponse):
        return JSONResponse(
            content=generator.model_dump(), status_code=generator.error.code
        )
    elif isinstance(generator, RerankResponse):
        return JSONResponse(content=generator.model_dump())

    assert_never(generator)


@router.post(
    "/v1/rerank",
    dependencies=[Depends(validate_json_request)],
    responses={
        HTTPStatus.BAD_REQUEST.value: {"model": ErrorResponse},
        HTTPStatus.INTERNAL_SERVER_ERROR.value: {"model": ErrorResponse},
    },
)
@with_cancellation
async def do_rerank_v1(request: RerankRequest, raw_request: Request):
    logger.warning_once(
        "To indicate that the rerank API is not part of the standard OpenAI"
        " API, we have located it at `/rerank`. Please update your client "
        "accordingly. (Note: Conforms to JinaAI rerank API)"
    )

    return await do_rerank(request, raw_request)


@router.post(
    "/v2/rerank",
    dependencies=[Depends(validate_json_request)],
    responses={
        HTTPStatus.BAD_REQUEST.value: {"model": ErrorResponse},
        HTTPStatus.INTERNAL_SERVER_ERROR.value: {"model": ErrorResponse},
    },
)
@with_cancellation
async def do_rerank_v2(request: RerankRequest, raw_request: Request):
    return await do_rerank(request, raw_request)


if envs.VLLM_SERVER_DEV_MODE:
    logger.warning(
        "SECURITY WARNING: Development endpoints are enabled! "
        "This should NOT be used in production!"
    )

    PydanticVllmConfig = pydantic.TypeAdapter(VllmConfig)

    @router.get("/server_info")
    async def show_server_info(
        raw_request: Request,
        config_format: Annotated[Literal["text", "json"], Query()] = "text",
    ):
        vllm_config: VllmConfig = raw_request.app.state.vllm_config
        server_info = {
            "vllm_config": str(vllm_config)
            if config_format == "text"
            else PydanticVllmConfig.dump_python(vllm_config, mode="json", fallback=str)
            # fallback=str is needed to handle e.g. torch.dtype
        }
        return JSONResponse(content=server_info)

    @router.post("/reset_prefix_cache")
    async def reset_prefix_cache(raw_request: Request):
        """
        Reset the prefix cache. Note that we currently do not check if the
        prefix cache is successfully reset in the API server.
        """
        logger.info("Resetting prefix cache...")
        await engine_client(raw_request).reset_prefix_cache()
        return Response(status_code=200)

    @router.post("/reset_mm_cache")
    async def reset_mm_cache(raw_request: Request):
        """
        Reset the multi-modal cache. Note that we currently do not check if the
        multi-modal cache is successfully reset in the API server.
        """
        logger.info("Resetting multi-modal cache...")
        await engine_client(raw_request).reset_mm_cache()
        return Response(status_code=200)

    @router.post("/sleep")
    async def sleep(raw_request: Request):
        # get POST params
        level = raw_request.query_params.get("level", "1")
        await engine_client(raw_request).sleep(int(level))
        # FIXME: in v0 with frontend multiprocessing, the sleep command
        # is sent but does not finish yet when we return a response.
        return Response(status_code=200)

    @router.post("/wake_up")
    async def wake_up(raw_request: Request):
        tags = raw_request.query_params.getlist("tags")
        if tags == []:
            # set to None to wake up all tags if no tags are provided
            tags = None
        logger.info("wake up the engine with tags: %s", tags)
        await engine_client(raw_request).wake_up(tags)
        # FIXME: in v0 with frontend multiprocessing, the wake-up command
        # is sent but does not finish yet when we return a response.
        return Response(status_code=200)

    @router.get("/is_sleeping")
    async def is_sleeping(raw_request: Request):
        logger.info("check whether the engine is sleeping")
        is_sleeping = await engine_client(raw_request).is_sleeping()
        return JSONResponse(content={"is_sleeping": is_sleeping})

    @router.post("/collective_rpc")
    async def collective_rpc(raw_request: Request):
        try:
            body = await raw_request.json()
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST.value,
                detail=f"JSON decode error: {e}",
            ) from e
        method = body.get("method")
        if method is None:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST.value,
                detail="Missing 'method' in request body",
            )
        # For security reason, only serialized string args/kwargs are passed.
        # User-defined `method` is responsible for deserialization if needed.
        args: list[str] = body.get("args", [])
        kwargs: dict[str, str] = body.get("kwargs", {})
        timeout: float | None = body.get("timeout")
        results = await engine_client(raw_request).collective_rpc(
            method=method, timeout=timeout, args=tuple(args), kwargs=kwargs
        )
        if results is None:
            return Response(status_code=200)
        response: list[Any] = []
        for result in results:
            if result is None or isinstance(result, (dict, list)):
                response.append(result)
            else:
                response.append(str(result))
        return JSONResponse(content={"results": response})


@router.post(
    "/scale_elastic_ep",
    dependencies=[Depends(validate_json_request)],
    responses={
        HTTPStatus.OK.value: {"model": dict},
        HTTPStatus.BAD_REQUEST.value: {"model": ErrorResponse},
        HTTPStatus.REQUEST_TIMEOUT.value: {"model": ErrorResponse},
        HTTPStatus.INTERNAL_SERVER_ERROR.value: {"model": ErrorResponse},
    },
)
async def scale_elastic_ep(raw_request: Request):
    try:
        body = await raw_request.json()
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail="Invalid JSON format") from e  # noqa: B904

    new_data_parallel_size = body.get("new_data_parallel_size")
    drain_timeout = body.get("drain_timeout", 120)  # Default 2 minutes

    if new_data_parallel_size is None:
        raise HTTPException(
            status_code=400, detail="new_data_parallel_size is required"
        )

    if not isinstance(new_data_parallel_size, int) or new_data_parallel_size <= 0:
        raise HTTPException(
            status_code=400, detail="new_data_parallel_size must be a positive integer"
        )

    if not isinstance(drain_timeout, int) or drain_timeout <= 0:
        raise HTTPException(
            status_code=400, detail="drain_timeout must be a positive integer"
        )

    # Set scaling flag to prevent new requests
    global _scaling_elastic_ep
    _scaling_elastic_ep = True
    client = engine_client(raw_request)
    try:
        await client.scale_elastic_ep(new_data_parallel_size, drain_timeout)
        return JSONResponse(
            {
                "message": f"Scaled to {new_data_parallel_size} data parallel engines",
            }
        )
    except TimeoutError as e:
        raise HTTPException(
            status_code=408,
            detail="Scale failed due to request drain timeout "
            f"after {drain_timeout} seconds",
        ) from e
    except Exception as e:
        logger.error("Scale failed: %s", e)
        raise HTTPException(status_code=500, detail="Scale failed") from e
    finally:
        _scaling_elastic_ep = False


@router.post("/is_scaling_elastic_ep")
async def is_scaling_elastic_ep(raw_request: Request):
    return JSONResponse({"is_scaling_elastic_ep": _scaling_elastic_ep})


# TODO: RequestType = TypeForm[BaseModel] when recognized by type checkers
# (requires typing_extensions >= 4.13)
RequestType = Any
GetHandlerFn = Callable[[Request], OpenAIServing | None]
EndpointFn = Callable[[RequestType, Request], Awaitable[Any]]

# NOTE: Items defined earlier take higher priority
INVOCATION_TYPES: list[tuple[RequestType, tuple[GetHandlerFn, EndpointFn]]] = [
    (ChatCompletionRequest, (chat, create_chat_completion)),
    (CompletionRequest, (completion, create_completion)),
    (EmbeddingRequest, (embedding, create_embedding)),
    (ClassificationRequest, (classify, create_classify)),
    (ScoreRequest, (score, create_score)),
    (RerankRequest, (rerank, do_rerank)),
    (PoolingRequest, (pooling, create_pooling)),
]

# NOTE: Construct the TypeAdapters only once
INVOCATION_VALIDATORS = [
    (pydantic.TypeAdapter(request_type), (get_handler, endpoint))
    for request_type, (get_handler, endpoint) in INVOCATION_TYPES
]


@router.post(
    "/inference/v1/generate",
    dependencies=[Depends(validate_json_request)],
    responses={
        HTTPStatus.OK.value: {"content": {"text/event-stream": {}}},
        HTTPStatus.BAD_REQUEST.value: {"model": ErrorResponse},
        HTTPStatus.NOT_FOUND.value: {"model": ErrorResponse},
        HTTPStatus.INTERNAL_SERVER_ERROR.value: {"model": ErrorResponse},
    },
)
@with_cancellation
@load_aware_call
async def generate(request: GenerateRequest, raw_request: Request):
    handler = generate_tokens(raw_request)
    if handler is None:
        return base(raw_request).create_error_response(
            message="The model does not support generate tokens API"
        )
    try:
        generator = await handler.serve_tokens(request, raw_request)
    except Exception as e:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR.value, detail=str(e)
        ) from e
    if isinstance(generator, ErrorResponse):
        return JSONResponse(
            content=generator.model_dump(), status_code=generator.error.code
        )

    elif isinstance(generator, GenerateResponse):
        return JSONResponse(content=generator.model_dump())

    return StreamingResponse(content=generator, media_type="text/event-stream")


if envs.VLLM_TORCH_PROFILER_DIR:
    logger.warning_once(
        "Torch Profiler is enabled in the API server. This should ONLY be "
        "used for local development!"
    )
elif envs.VLLM_TORCH_CUDA_PROFILE:
    logger.warning_once(
        "CUDA Profiler is enabled in the API server. This should ONLY be "
        "used for local development!"
    )
if envs.VLLM_TORCH_PROFILER_DIR or envs.VLLM_TORCH_CUDA_PROFILE:

    @router.post("/start_profile")
    async def start_profile(raw_request: Request):
        logger.info("Starting profiler...")
        await engine_client(raw_request).start_profile()
        logger.info("Profiler started.")
        return Response(status_code=200)

    @router.post("/stop_profile")
    async def stop_profile(raw_request: Request):
        logger.info("Stopping profiler...")
        await engine_client(raw_request).stop_profile()
        logger.info("Profiler stopped.")
        return Response(status_code=200)


def load_log_config(log_config_file: str | None) -> dict | None:
    if not log_config_file:
        return None
    try:
        with open(log_config_file) as f:
            return json.load(f)
    except Exception as e:
        logger.warning(
            "Failed to load log config from file %s: error %s", log_config_file, e
        )
        return None


class AuthenticationMiddleware:
    """
    Pure ASGI middleware that authenticates each request by checking
    if the Authorization Bearer token exists and equals anyof "{api_key}".

    Notes
    -----
    There are two cases in which authentication is skipped:
        1. The HTTP method is OPTIONS.
        2. The request path doesn't start with /v1 (e.g. /health).
    """

    def __init__(self, app: ASGIApp, tokens: list[str]) -> None:
        self.app = app
        self.api_tokens = [hashlib.sha256(t.encode("utf-8")).digest() for t in tokens]

    def verify_token(self, headers: Headers) -> bool:
        authorization_header_value = headers.get("Authorization")
        if not authorization_header_value:
            return False

        scheme, _, param = authorization_header_value.partition(" ")
        if scheme.lower() != "bearer":
            return False

        param_hash = hashlib.sha256(param.encode("utf-8")).digest()

        token_match = False
        for token_hash in self.api_tokens:
            token_match |= secrets.compare_digest(param_hash, token_hash)

        return token_match

    def __call__(self, scope: Scope, receive: Receive, send: Send) -> Awaitable[None]:
        if scope["type"] not in ("http", "websocket") or scope["method"] == "OPTIONS":
            # scope["type"] can be "lifespan" or "startup" for example,
            # in which case we don't need to do anything
            return self.app(scope, receive, send)
        root_path = scope.get("root_path", "")
        url_path = URL(scope=scope).path.removeprefix(root_path)
        headers = Headers(scope=scope)
        # Type narrow to satisfy mypy.
        if url_path.startswith("/v1") and not self.verify_token(headers):
            response = JSONResponse(content={"error": "Unauthorized"}, status_code=401)
            return response(scope, receive, send)
        return self.app(scope, receive, send)


class XRequestIdMiddleware:
    """
    Middleware the set's the X-Request-Id header for each response
    to a random uuid4 (hex) value if the header isn't already
    present in the request, otherwise use the provided request id.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    def __call__(self, scope: Scope, receive: Receive, send: Send) -> Awaitable[None]:
        if scope["type"] not in ("http", "websocket"):
            return self.app(scope, receive, send)

        # Extract the request headers.
        request_headers = Headers(scope=scope)

        async def send_with_request_id(message: Message) -> None:
            """
            Custom send function to mutate the response headers
            and append X-Request-Id to it.
            """
            if message["type"] == "http.response.start":
                response_headers = MutableHeaders(raw=message["headers"])
                request_id = request_headers.get("X-Request-Id", uuid.uuid4().hex)
                response_headers.append("X-Request-Id", request_id)
            await send(message)

        return self.app(scope, receive, send_with_request_id)


# Global variable to track scaling state
_scaling_elastic_ep = False


class ScalingMiddleware:
    """
    Middleware that checks if the model is currently scaling and
    returns a 503 Service Unavailable response if it is.

    This middleware applies to all HTTP requests and prevents
    processing when the model is in a scaling state.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    def __call__(self, scope: Scope, receive: Receive, send: Send) -> Awaitable[None]:
        if scope["type"] != "http":
            return self.app(scope, receive, send)

        # Check global scaling state
        global _scaling_elastic_ep
        if _scaling_elastic_ep:
            # Return 503 Service Unavailable response
            response = JSONResponse(
                content={
                    "error": "The model is currently scaling. Please try again later."
                },
                status_code=503,
            )
            return response(scope, receive, send)

        return self.app(scope, receive, send)


def _extract_content_from_chunk(chunk_data: dict) -> str:
    """Extract content from a streaming response chunk."""
    try:
        from vllm.entrypoints.openai.protocol import (
            ChatCompletionStreamResponse,
            CompletionStreamResponse,
        )

        # Try using Completion types for type-safe parsing
        if chunk_data.get("object") == "chat.completion.chunk":
            chat_response = ChatCompletionStreamResponse.model_validate(chunk_data)
            if chat_response.choices and chat_response.choices[0].delta.content:
                return chat_response.choices[0].delta.content
        elif chunk_data.get("object") == "text_completion":
            completion_response = CompletionStreamResponse.model_validate(chunk_data)
            if completion_response.choices and completion_response.choices[0].text:
                return completion_response.choices[0].text
    except pydantic.ValidationError:
        # Fallback to manual parsing
        if "choices" in chunk_data and chunk_data["choices"]:
            choice = chunk_data["choices"][0]
            if "delta" in choice and choice["delta"].get("content"):
                return choice["delta"]["content"]
            elif choice.get("text"):
                return choice["text"]
    return ""


class SSEDecoder:
    """Robust Server-Sent Events decoder for streaming responses."""

    def __init__(self, max_buffer_bytes: int = 1_000_000):
        self.buffer = ""
        self.content_buffer = []
        self._current_event: dict[str, Any] = {"event": None, "data_lines": []}
        self.max_buffer_bytes = max_buffer_bytes

    def decode_chunk(self, chunk: bytes) -> list[dict]:
        """Decode a chunk of SSE data and return parsed events."""
        import json

        chunk_str = chunk.decode("utf-8", errors="ignore")
        if not chunk_str:
            return []

        self.buffer += chunk_str
        if len(self.buffer) > self.max_buffer_bytes:
            self.buffer = self.buffer[-self.max_buffer_bytes :]

        events: list[dict] = []

        # Process complete lines
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            line = line.rstrip("\r")  # Handle CRLF

            if line.startswith("event:"):
                self._current_event["event"] = line[6:].strip()
            elif line.startswith("data:"):
                self._current_event.setdefault("data_lines", []).append(
                    line[6:].strip("\r")
                )
            elif line == "":
                finalized = self._finalize_event()
                if finalized is not None:
                    if finalized["type"] == "done":
                        events.append(finalized)
                    elif finalized["type"] == "data":
                        data_str = finalized["data"]
                        if data_str == "[DONE]":
                            events.append({"type": "done"})
                        elif data_str:
                            try:
                                event_data = json.loads(data_str)
                                events.append({"type": "data", "data": event_data})
                            except json.JSONDecodeError:
                                continue
        return events

    def _finalize_event(self) -> dict | None:
        data_lines = self._current_event.get("data_lines") or []
        if not data_lines:
            self._current_event = {"event": None, "data_lines": []}
            return None
        data_str = "\n".join(data_lines).strip()
        self._current_event = {"event": None, "data_lines": []}
        return {"type": "done" if data_str == "[DONE]" else "data", "data": data_str}

    def extract_content(self, event_data: dict) -> str:
        """Extract content from event data."""
        return _extract_content_from_chunk(event_data)

    def add_content(self, content: str) -> None:
        """Add content to the buffer."""
        if content:
            self.content_buffer.append(content)

    def get_complete_content(self) -> str:
        """Get the complete buffered content."""
        return "".join(self.content_buffer)


def _log_streaming_response(response, response_body: list) -> None:
    """Log streaming response with robust SSE parsing."""
    from starlette.concurrency import iterate_in_threadpool

    sse_decoder = SSEDecoder()
    chunk_count = 0

    def buffered_iterator():
        nonlocal chunk_count

        for chunk in response_body:
            chunk_count += 1
            yield chunk

            # Parse SSE events from chunk
            events = sse_decoder.decode_chunk(chunk)

            for event in events:
                if event["type"] == "data":
                    content = sse_decoder.extract_content(event["data"])
                    sse_decoder.add_content(content)
                elif event["type"] == "done":
                    # Log complete content when done
                    full_content = sse_decoder.get_complete_content()
                    if full_content:
                        # Truncate if too long
                        if len(full_content) > 2048:
                            full_content = full_content[:2048] + ""
                            "...[truncated]"
                        logger.info(
                            "response_body={streaming_complete: content=%r, chunks=%d}",
                            full_content,
                            chunk_count,
                        )
                    else:
                        logger.info(
                            "response_body={streaming_complete: no_content, chunks=%d}",
                            chunk_count,
                        )
                    return

    response.body_iterator = iterate_in_threadpool(buffered_iterator())
    logger.info("response_body={streaming_started: chunks=%d}", len(response_body))


def _log_non_streaming_response(response_body: list) -> None:
    """Log non-streaming response."""
    try:
        decoded_body = response_body[0].decode()
        logger.info("response_body={%s}", decoded_body)
    except UnicodeDecodeError:
        logger.info("response_body={<binary_data>}")


def build_app(args: Namespace) -> FastAPI:
    if args.disable_fastapi_docs:
        app = FastAPI(
            openapi_url=None, docs_url=None, redoc_url=None, lifespan=lifespan
        )
    else:
        app = FastAPI(lifespan=lifespan)

    if envs.VLLM_ALLOW_RUNTIME_LORA_UPDATING:
        logger.warning(
            "LoRA dynamic loading & unloading is enabled in the API server. "
            "This should ONLY be used for local development!"
        )
        from vllm.entrypoints.dynamic_lora import register_dynamic_lora_routes

        register_dynamic_lora_routes(router)

    from vllm.entrypoints.sagemaker.routes import register_sagemaker_routes

    register_sagemaker_routes(router)

    app.include_router(router)
    app.root_path = args.root_path

    mount_metrics(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=args.allowed_origins,
        allow_credentials=args.allow_credentials,
        allow_methods=args.allowed_methods,
        allow_headers=args.allowed_headers,
    )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException):
        err = ErrorResponse(
            error=ErrorInfo(
                message=exc.detail,
                type=HTTPStatus(exc.status_code).phrase,
                code=exc.status_code,
            )
        )
        return JSONResponse(err.model_dump(), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_: Request, exc: RequestValidationError):
        # Log full traceback for debugging
        logger.exception("RequestValidationError occurred:")

        exc_str = str(exc)
        errors_str = str(exc.errors())

        if exc.errors() and errors_str and errors_str != exc_str:
            message = f"{exc_str} {errors_str}"
        else:
            message = exc_str

        err = ErrorResponse(
            error=ErrorInfo(
                message=message,
                type=HTTPStatus.BAD_REQUEST.phrase,
                code=HTTPStatus.BAD_REQUEST,
            )
        )
        return JSONResponse(err.model_dump(), status_code=HTTPStatus.BAD_REQUEST)

    @app.exception_handler(Exception)
    async def general_exception_handler(_: Request, exc: Exception):
        # Log full traceback for all unhandled exceptions
        logger.exception("Unhandled exception occurred:")

        err = ErrorResponse(
            error=ErrorInfo(
                message=str(exc),
                type="Internal Server Error",
                code=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
        )
        return JSONResponse(err.model_dump(), status_code=HTTPStatus.INTERNAL_SERVER_ERROR)

    # Ensure --api-key option from CLI takes precedence over VLLM_API_KEY
    if tokens := [key for key in (args.api_key or [envs.VLLM_API_KEY]) if key]:
        app.add_middleware(AuthenticationMiddleware, tokens=tokens)

    if args.enable_request_id_headers:
        app.add_middleware(XRequestIdMiddleware)

    # Add scaling middleware to check for scaling state
    app.add_middleware(ScalingMiddleware)

    if envs.VLLM_DEBUG_LOG_API_SERVER_RESPONSE:
        logger.warning(
            "CAUTION: Enabling log response in the API Server. "
            "This can include sensitive information and should be "
            "avoided in production."
        )

        @app.middleware("http")
        async def log_response(request: Request, call_next):
            response = await call_next(request)
            response_body = [section async for section in response.body_iterator]
            response.body_iterator = iterate_in_threadpool(iter(response_body))
            # Check if this is a streaming response by looking at content-type
            content_type = response.headers.get("content-type", "")
            is_streaming = content_type == "text/event-stream; charset=utf-8"

            # Log response body based on type
            if not response_body:
                logger.info("response_body={<empty>}")
            elif is_streaming:
                _log_streaming_response(response, response_body)
            else:
                _log_non_streaming_response(response_body)
            return response

    for middleware in args.middleware:
        module_path, object_name = middleware.rsplit(".", 1)
        imported = getattr(importlib.import_module(module_path), object_name)
        if inspect.isclass(imported):
            app.add_middleware(imported)  # type: ignore[arg-type]
        elif inspect.iscoroutinefunction(imported):
            app.middleware("http")(imported)
        else:
            raise ValueError(
                f"Invalid middleware {middleware}. Must be a function or a class."
            )

    app = sagemaker_standards.bootstrap(app)
    # Optional endpoints
    if args.tokens_only:

        @app.post("/abort_requests")
        async def abort_requests(raw_request: Request):
            """
            Abort one or more requests. To be used in a
            Disaggregated Everything setup.
            """
            try:
                body = await raw_request.json()
            except json.JSONDecodeError as e:
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST.value,
                    detail=f"JSON decode error: {e}",
                ) from e
            request_ids = body.get("request_ids")
            if request_ids is None:
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST.value,
                    detail="Missing 'request_ids' in request body",
                )
            # Abort requests in background
            asyncio.create_task(engine_client(raw_request).abort(request_ids))
            return Response(status_code=200)

    return app


async def init_app_state(
    engine_client: EngineClient,
    state: State,
    args: Namespace,
) -> None:
    vllm_config = engine_client.vllm_config

    if args.served_model_name is not None:
        served_model_names = args.served_model_name
    else:
        served_model_names = [args.model]

    if args.enable_log_requests:
        request_logger = RequestLogger(max_log_len=args.max_log_len)
    else:
        request_logger = None

    base_model_paths = [
        BaseModelPath(name=name, model_path=args.model) for name in served_model_names
    ]

    state.engine_client = engine_client
    state.log_stats = not args.disable_log_stats
    state.vllm_config = vllm_config
    state.azure_api_enabled = args.enable_azure_api
    state.azure_region = args.azure_region

    supported_tasks = await engine_client.get_supported_tasks()
    logger.info("Supported tasks: %s", supported_tasks)

    resolved_chat_template = await process_chat_template(
        args.chat_template, engine_client, vllm_config.model_config
    )

    if args.tool_server == "demo":
        tool_server: ToolServer | None = DemoToolServer()
        assert isinstance(tool_server, DemoToolServer)
        await tool_server.init_and_validate()
    elif args.tool_server:
        tool_server = MCPToolServer()
        await tool_server.add_tool_server(args.tool_server)
    else:
        tool_server = None

    # Merge default_mm_loras into the static lora_modules
    default_mm_loras = (
        vllm_config.lora_config.default_mm_loras
        if vllm_config.lora_config is not None
        else {}
    )

    default_mm_loras = (
        vllm_config.lora_config.default_mm_loras
        if vllm_config.lora_config is not None
        else {}
    )
    lora_modules = process_lora_modules(args.lora_modules, default_mm_loras)

    state.openai_serving_models = OpenAIServingModels(
        engine_client=engine_client,
        base_model_paths=base_model_paths,
        lora_modules=lora_modules,
    )
    await state.openai_serving_models.init_static_loras()

    rate_limits_config = None
    if args.rate_limits_config:
        with open(args.rate_limits_config, "r", encoding="utf-8") as f:
            rate_limits_config = json.load(f)

    image_service_config = None
    if args.image_service_config:
        try:
            with open(args.image_service_config, "r", encoding="utf-8") as f:
                image_service_config = json.load(f)
        except OSError as exc:
            raise RuntimeError(
                f"Unable to read image service config ({args.image_service_config}): {exc}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Image service config must be valid JSON ({args.image_service_config})."
            ) from exc

    state.openai_serving_responses = (
        OpenAIServingResponses(
            engine_client,
            state.openai_serving_models,
            request_logger=request_logger,
            chat_template=resolved_chat_template,
            chat_template_content_format=args.chat_template_content_format,
            return_tokens_as_token_ids=args.return_tokens_as_token_ids,
            enable_auto_tools=args.enable_auto_tool_choice,
            tool_parser=args.tool_call_parser,
            tool_server=tool_server,
            reasoning_parser=args.structured_outputs_config.reasoning_parser,
            enable_prompt_tokens_details=args.enable_prompt_tokens_details,
            enable_force_include_usage=args.enable_force_include_usage,
            enable_log_outputs=args.enable_log_outputs,
            log_error_stack=args.log_error_stack,
            legacy_reasoning_events=args.legacy_reasoning_events,
            reasoning_encryption_key=args.reasoning_encryption_key,
            enable_rate_limit_events=args.enable_rate_limit_events,
            rate_limit_requests_per_minute=args.rate_limit_requests_per_minute,
            rate_limit_requests_per_hour=args.rate_limit_requests_per_hour,
            rate_limit_tokens_per_minute=args.rate_limit_tokens_per_minute,
            tool_outputs_timeout=args.responses_tool_timeout,
            responses_session_ttl=args.responses_session_ttl,
            rate_limits_config=rate_limits_config,
            enable_computer_call=args.enable_computer_call,
            image_service_config=image_service_config,
            disable_responses_store=args.disable_responses_store,
            responses_store_ttl=args.responses_store_ttl,
            responses_store_max_entries=args.responses_store_max_entries,
            responses_store_max_bytes=args.responses_store_max_bytes,
            default_openai_organization=args.default_openai_organization,
            default_openai_version=args.default_openai_version,
            max_request_body_tokens=args.max_request_body_tokens,
            max_request_body_bytes=args.max_request_body_bytes,
            max_tool_output_bytes=args.max_tool_output_bytes,
            responses_max_active_sessions=args.responses_max_active_sessions,
            max_stream_event_bytes=args.max_stream_event_bytes,
            responses_stream_buffer_max_bytes=(
                args.responses_stream_buffer_max_bytes
            ),
            compatibility_mode=args.responses_compatibility_mode,
            ping_interval_seconds=args.responses_ping_interval_seconds,
            default_service_tier=args.responses_default_service_tier,
            allowed_service_tiers=args.responses_allowed_service_tiers,
        )
        if "generate" in supported_tasks
        else None
    )
    state.openai_serving_chat = (
        OpenAIServingChat(
            engine_client,
            state.openai_serving_models,
            args.response_role,
            request_logger=request_logger,
            chat_template=resolved_chat_template,
            chat_template_content_format=args.chat_template_content_format,
            trust_request_chat_template=args.trust_request_chat_template,
            return_tokens_as_token_ids=args.return_tokens_as_token_ids,
            enable_auto_tools=args.enable_auto_tool_choice,
            exclude_tools_when_tool_choice_none=args.exclude_tools_when_tool_choice_none,
            tool_parser=args.tool_call_parser,
            reasoning_parser=args.structured_outputs_config.reasoning_parser,
            enable_prompt_tokens_details=args.enable_prompt_tokens_details,
            enable_force_include_usage=args.enable_force_include_usage,
            enable_log_outputs=args.enable_log_outputs,
            log_error_stack=args.log_error_stack,
        )
        if "generate" in supported_tasks
        else None
    )
    state.openai_serving_completion = (
        OpenAIServingCompletion(
            engine_client,
            state.openai_serving_models,
            request_logger=request_logger,
            return_tokens_as_token_ids=args.return_tokens_as_token_ids,
            enable_prompt_tokens_details=args.enable_prompt_tokens_details,
            enable_force_include_usage=args.enable_force_include_usage,
            log_error_stack=args.log_error_stack,
        )
        if "generate" in supported_tasks
        else None
    )
    state.openai_serving_pooling = (
        OpenAIServingPooling(
            engine_client,
            state.openai_serving_models,
            supported_tasks=supported_tasks,
            request_logger=request_logger,
            chat_template=resolved_chat_template,
            chat_template_content_format=args.chat_template_content_format,
            trust_request_chat_template=args.trust_request_chat_template,
            log_error_stack=args.log_error_stack,
        )
        if any(task in POOLING_TASKS for task in supported_tasks)
        else None
    )
    state.conversation_store = ConversationStore()
    state.openai_serving_embedding = (
        OpenAIServingEmbedding(
            engine_client,
            state.openai_serving_models,
            request_logger=request_logger,
            chat_template=resolved_chat_template,
            chat_template_content_format=args.chat_template_content_format,
            trust_request_chat_template=args.trust_request_chat_template,
            log_error_stack=args.log_error_stack,
        )
        if "embed" in supported_tasks
        else None
    )
    state.openai_serving_classification = (
        ServingClassification(
            engine_client,
            state.openai_serving_models,
            request_logger=request_logger,
            chat_template=resolved_chat_template,
            chat_template_content_format=args.chat_template_content_format,
            trust_request_chat_template=args.trust_request_chat_template,
            log_error_stack=args.log_error_stack,
        )
        if "classify" in supported_tasks
        else None
    )
    state.openai_serving_scores = (
        ServingScores(
            engine_client,
            state.openai_serving_models,
            request_logger=request_logger,
            log_error_stack=args.log_error_stack,
        )
        if ("embed" in supported_tasks or "score" in supported_tasks)
        else None
    )
    state.openai_serving_tokenization = OpenAIServingTokenization(
        engine_client,
        state.openai_serving_models,
        request_logger=request_logger,
        chat_template=resolved_chat_template,
        chat_template_content_format=args.chat_template_content_format,
        trust_request_chat_template=args.trust_request_chat_template,
        log_error_stack=args.log_error_stack,
    )
    state.openai_serving_transcription = (
        OpenAIServingTranscription(
            engine_client,
            state.openai_serving_models,
            request_logger=request_logger,
            log_error_stack=args.log_error_stack,
            enable_force_include_usage=args.enable_force_include_usage,
        )
        if "transcription" in supported_tasks
        else None
    )
    state.openai_serving_translation = (
        OpenAIServingTranslation(
            engine_client,
            state.openai_serving_models,
            request_logger=request_logger,
            log_error_stack=args.log_error_stack,
            enable_force_include_usage=args.enable_force_include_usage,
        )
        if "transcription" in supported_tasks
        else None
    )
    state.anthropic_serving_messages = (
        AnthropicServingMessages(
            engine_client,
            state.openai_serving_models,
            args.response_role,
            request_logger=request_logger,
            chat_template=resolved_chat_template,
            chat_template_content_format=args.chat_template_content_format,
            return_tokens_as_token_ids=args.return_tokens_as_token_ids,
            enable_auto_tools=args.enable_auto_tool_choice,
            tool_parser=args.tool_call_parser,
            reasoning_parser=args.structured_outputs_config.reasoning_parser,
            enable_prompt_tokens_details=args.enable_prompt_tokens_details,
            enable_force_include_usage=args.enable_force_include_usage,
        )
        if "generate" in supported_tasks
        else None
    )
    state.serving_tokens = (
        ServingTokens(
            engine_client,
            state.openai_serving_models,
            request_logger=request_logger,
            return_tokens_as_token_ids=args.return_tokens_as_token_ids,
            log_error_stack=args.log_error_stack,
            enable_prompt_tokens_details=args.enable_prompt_tokens_details,
            enable_log_outputs=args.enable_log_outputs,
            force_no_detokenize=args.tokens_only,
        )
        if "generate" in supported_tasks
        else None
    )

    state.enable_server_load_tracking = args.enable_server_load_tracking
    state.server_load_metrics = 0


def create_server_socket(addr: tuple[str, int]) -> socket.socket:
    family = socket.AF_INET
    if is_valid_ipv6_address(addr[0]):
        family = socket.AF_INET6

    sock = socket.socket(family=family, type=socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    sock.bind(addr)

    return sock


def create_server_unix_socket(path: str) -> socket.socket:
    sock = socket.socket(family=socket.AF_UNIX, type=socket.SOCK_STREAM)
    sock.bind(path)
    return sock


def validate_api_server_args(args):
    valid_tool_parses = ToolParserManager.list_registered()
    if args.enable_auto_tool_choice and args.tool_call_parser not in valid_tool_parses:
        raise KeyError(
            f"invalid tool call parser: {args.tool_call_parser} "
            f"(chose from {{ {','.join(valid_tool_parses)} }})"
        )

    valid_reasoning_parsers = ReasoningParserManager.list_registered()
    if (
        reasoning_parser := args.structured_outputs_config.reasoning_parser
    ) and reasoning_parser not in valid_reasoning_parsers:
        raise KeyError(
            f"invalid reasoning parser: {reasoning_parser} "
            f"(chose from {{ {','.join(valid_reasoning_parsers)} }})"
        )


def setup_server(args):
    """Validate API server args, set up signal handler, create socket
    ready to serve."""

    logger.info("vLLM API server version %s", VLLM_VERSION)
    log_non_default_args(args)

    if args.tool_parser_plugin and len(args.tool_parser_plugin) > 3:
        ToolParserManager.import_tool_parser(args.tool_parser_plugin)

    if args.reasoning_parser_plugin and len(args.reasoning_parser_plugin) > 3:
        ReasoningParserManager.import_reasoning_parser(args.reasoning_parser_plugin)

    validate_api_server_args(args)

    # workaround to make sure that we bind the port before the engine is set up.
    # This avoids race conditions with ray.
    # see https://github.com/vllm-project/vllm/issues/8204
    if args.uds:
        sock = create_server_unix_socket(args.uds)
    else:
        sock_addr = (args.host or "", args.port)
        sock = create_server_socket(sock_addr)

    # workaround to avoid footguns where uvicorn drops requests with too
    # many concurrent requests active
    set_ulimit()

    def signal_handler(*_) -> None:
        # Interrupt server on sigterm while initializing
        raise KeyboardInterrupt("terminated")

    signal.signal(signal.SIGTERM, signal_handler)

    if args.uds:
        listen_address = f"unix:{args.uds}"
    else:
        addr, port = sock_addr
        is_ssl = args.ssl_keyfile and args.ssl_certfile
        host_part = f"[{addr}]" if is_valid_ipv6_address(addr) else addr or "0.0.0.0"
        listen_address = f"http{'s' if is_ssl else ''}://{host_part}:{port}"
    return listen_address, sock


async def run_server(args, **uvicorn_kwargs) -> None:
    """Run a single-worker API server."""

    # Add process-specific prefix to stdout and stderr.
    decorate_logs("APIServer")

    # Suppress verbose logs from model_hosting_container_standards
    logging.getLogger("model_hosting_container_standards").setLevel(logging.ERROR)

    listen_address, sock = setup_server(args)
    await run_server_worker(listen_address, sock, args, **uvicorn_kwargs)


async def run_server_worker(
    listen_address, sock, args, client_config=None, **uvicorn_kwargs
) -> None:
    """Run a single API server worker."""

    if args.tool_parser_plugin and len(args.tool_parser_plugin) > 3:
        ToolParserManager.import_tool_parser(args.tool_parser_plugin)

    if args.reasoning_parser_plugin and len(args.reasoning_parser_plugin) > 3:
        ReasoningParserManager.import_reasoning_parser(args.reasoning_parser_plugin)

    # Load logging config for uvicorn if specified
    log_config = load_log_config(args.log_config_file)
    if log_config is not None:
        uvicorn_kwargs["log_config"] = log_config

    async with build_async_engine_client(
        args,
        client_config=client_config,
    ) as engine_client:
        maybe_register_tokenizer_info_endpoint(args)
        app = build_app(args)

        await init_app_state(engine_client, app.state, args)

        logger.info(
            "Starting vLLM API server %d on %s",
            engine_client.vllm_config.parallel_config._api_process_rank,
            listen_address,
        )
        shutdown_task = await serve_http(
            app,
            sock=sock,
            enable_ssl_refresh=args.enable_ssl_refresh,
            host=args.host,
            port=args.port,
            log_level=args.uvicorn_log_level,
            # NOTE: When the 'disable_uvicorn_access_log' value is True,
            # no access log will be output.
            access_log=not args.disable_uvicorn_access_log,
            timeout_keep_alive=envs.VLLM_HTTP_TIMEOUT_KEEP_ALIVE,
            ssl_keyfile=args.ssl_keyfile,
            ssl_certfile=args.ssl_certfile,
            ssl_ca_certs=args.ssl_ca_certs,
            ssl_cert_reqs=args.ssl_cert_reqs,
            h11_max_incomplete_event_size=args.h11_max_incomplete_event_size,
            h11_max_header_count=args.h11_max_header_count,
            **uvicorn_kwargs,
        )

    # NB: Await server shutdown only after the backend context is exited
    try:
        await shutdown_task
    finally:
        sock.close()


if __name__ == "__main__":
    # NOTE(simon):
    # This section should be in sync with vllm/entrypoints/cli/main.py for CLI
    # entrypoints.
    cli_env_setup()
    parser = FlexibleArgumentParser(
        description="vLLM OpenAI-Compatible RESTful API server."
    )
    parser = make_arg_parser(parser)
    args = parser.parse_args()
    validate_parsed_serve_args(args)

    uvloop.run(run_server(args))
def _apply_compatibility_shims(event_dict: dict[str, Any]) -> None:
    event_type = str(event_dict.get("type") or "")
    if event_type == "response.reasoning.delta":
        delta = event_dict.get("delta")
        if isinstance(delta, dict):
            event_dict["delta"] = delta.get("content", "")
    elif event_type == "response.reasoning.done":
        reasoning = event_dict.get("reasoning")
        if isinstance(reasoning, dict):
            event_dict["reasoning"] = reasoning.get("content", "")
    elif event_type == "response.reasoning.summary.delta":
        delta = event_dict.get("delta")
        if isinstance(delta, dict):
            event_dict["delta"] = delta.get("summary", "")
