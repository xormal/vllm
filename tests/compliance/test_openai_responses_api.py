# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project

"""OpenAI Responses API Compliance Suite.

These tests exercise the official `/v1/responses` workflow against a running
server. Set the following environment variables before running:

* `VLLM_COMPLIANCE_BASE_URL` – e.g. `http://localhost:8000/v1`
* `VLLM_COMPLIANCE_MODEL` – model identifier exposed by the server
* `VLLM_COMPLIANCE_API_KEY` (optional) – bearer token for Authorization header
* `VLLM_COMPLIANCE_ORG` (optional) – OpenAI-Organization header
"""

from __future__ import annotations

import os
from http import HTTPStatus

import httpx
import pytest
import pytest_asyncio

pytestmark = pytest.mark.compliance


def _require_env(var_name: str) -> str:
    value = os.getenv(var_name)
    if not value:
        pytest.skip(f"Set {var_name} to run compliance tests.")
    return value


def _base_headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    api_key = os.getenv("VLLM_COMPLIANCE_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    org = os.getenv("VLLM_COMPLIANCE_ORG")
    if org:
        headers["OpenAI-Organization"] = org
    return headers


def _merge_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = dict(_base_headers())
    if extra:
        headers.update(extra)
    return headers


@pytest.fixture(scope="session")
def compliance_base_url() -> str:
    """Base URL for the running Responses API server."""

    return _require_env("VLLM_COMPLIANCE_BASE_URL").rstrip("/")


@pytest.fixture(scope="session")
def compliance_model() -> str:
    """Model identifier used for compliance runs."""

    return _require_env("VLLM_COMPLIANCE_MODEL")


@pytest_asyncio.fixture(scope="session")
async def compliance_client(
    compliance_base_url: str,
) -> httpx.AsyncClient:
    async with httpx.AsyncClient(
        base_url=compliance_base_url,
        timeout=30.0,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def stored_response_id(
    compliance_client: httpx.AsyncClient,
    compliance_model: str,
) -> str:
    payload = {
        "model": compliance_model,
        "input": "Compliance suite stored response",
        "store": True,
    }
    response = await compliance_client.post(
        "/responses",
        headers=_merge_headers(),
        json=payload,
    )
    assert (
        response.status_code == HTTPStatus.OK
    ), f"Failed to create response: {response.text}"
    data = response.json()
    return data["id"]


@pytest.mark.spec_line(22)
@pytest.mark.asyncio
async def test_post_responses_returns_response_object(
    compliance_client: httpx.AsyncClient,
    compliance_model: str,
) -> None:
    payload = {"model": compliance_model, "input": "Compliance ping", "store": True}
    response = await compliance_client.post(
        "/responses",
        headers=_merge_headers(),
        json=payload,
    )
    assert response.status_code == HTTPStatus.OK, response.text
    data = response.json()
    assert data["id"].startswith("resp_")
    assert data["model"] == compliance_model


@pytest.mark.spec_line(23)
@pytest.mark.asyncio
async def test_tool_outputs_unknown_response_returns_not_found(
    compliance_client: httpx.AsyncClient,
) -> None:
    response = await compliance_client.post(
        "/responses/resp_nonexistent/tool_outputs",
        headers=_merge_headers(),
        json={"tool_call_id": "call_1", "output": []},
    )
    assert response.status_code in (
        HTTPStatus.NOT_FOUND,
        HTTPStatus.BAD_REQUEST,
    )


@pytest.mark.asyncio
async def test_get_responses_after_store(
    compliance_client: httpx.AsyncClient,
    stored_response_id: str,
) -> None:
    response = await compliance_client.get(
        f"/responses/{stored_response_id}",
        headers=_merge_headers(),
    )
    assert response.status_code == HTTPStatus.OK, response.text
    data = response.json()
    assert data["id"] == stored_response_id


@pytest.mark.asyncio
async def test_streaming_responses_emits_done(
    compliance_client: httpx.AsyncClient,
    compliance_model: str,
) -> None:
    payload = {
        "model": compliance_model,
        "input": "Stream compliance sample",
        "stream": True,
        "max_output_tokens": 16,
    }
    headers = _merge_headers({"Accept": "text/event-stream"})
    async with compliance_client.stream(
        "POST",
        "/responses",
        headers=headers,
        json=payload,
    ) as response:
        assert response.status_code == HTTPStatus.OK, await response.aread()
        saw_event = False
        saw_done = False
        async for line in response.aiter_lines():
            if line.startswith("event: response."):
                saw_event = True
            if line.strip() == "data: [DONE]":
                saw_done = True
                break
        assert saw_event, "Expected at least one SSE event."
        assert saw_done, "Expected terminal [DONE] chunk."


@pytest.mark.asyncio
async def test_request_id_header_is_echoed(
    compliance_client: httpx.AsyncClient,
    compliance_model: str,
) -> None:
    request_id = "compliance-" + os.urandom(4).hex()
    payload = {"model": compliance_model, "input": "Header validation"}
    response = await compliance_client.post(
        "/responses",
        headers=_merge_headers({"X-Request-Id": request_id}),
        json=payload,
    )
    # Endpoint should exist even if validation fails
    assert response.status_code in (
        HTTPStatus.OK,
        HTTPStatus.BAD_REQUEST,
    )
    assert response.headers.get("x-request-id") == request_id
