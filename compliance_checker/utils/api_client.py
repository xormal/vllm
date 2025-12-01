"""
API Client for connecting to vLLM server
"""

import json
import logging
from typing import Any, Dict, Iterator, Optional
from urllib.parse import urljoin

import httpx
import sseclient

logger = logging.getLogger(__name__)


class APIClient:
    """HTTP client for OpenAI Responses API testing."""

    def __init__(
        self,
        base_url: str,
        api_version: str = "v1",
        timeout: int = 30,
        api_key: Optional[str] = None,
        verify_ssl: bool = True,
    ):
        """Initialize API client.

        Args:
            base_url: Base URL of the server (e.g., http://192.168.228.43:8000)
            api_version: API version (default: v1)
            timeout: Request timeout in seconds
            api_key: Optional API key for authentication
            verify_ssl: Whether to verify SSL certificates
        """
        self.base_url = base_url.rstrip("/")
        self.api_version = api_version
        self.timeout = timeout
        self.verify_ssl = verify_ssl

        # Build headers
        self.headers = {
            "Content-Type": "application/json",
            "User-Agent": "vLLM-Compliance-Checker/1.0",
        }

        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"

        # Create HTTP client
        self.client = httpx.Client(
            timeout=timeout,
            verify=verify_ssl,
            follow_redirects=True,
        )

        logger.info(f"API Client initialized for {self.base_url}")

    def _build_url(self, endpoint: str) -> str:
        """Build full URL from endpoint."""
        # Remove leading slash from endpoint
        endpoint = endpoint.lstrip("/")

        # Add API version if not already in endpoint
        if not endpoint.startswith(self.api_version):
            endpoint = f"{self.api_version}/{endpoint}"

        return urljoin(f"{self.base_url}/", endpoint)

    def check_health(self) -> bool:
        """Check if server is reachable.

        Returns:
            True if server is healthy, False otherwise
        """
        try:
            url = urljoin(f"{self.base_url}/", "health")
            response = self.client.get(url, timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    def post(
        self,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        stream: bool = False,
    ) -> httpx.Response:
        """Send POST request.

        Args:
            endpoint: API endpoint (e.g., "/responses")
            data: JSON payload
            stream: Whether to stream response

        Returns:
            HTTP response object

        Raises:
            httpx.HTTPError: On HTTP errors
        """
        url = self._build_url(endpoint)
        headers = self.headers.copy()

        if stream:
            headers["Accept"] = "text/event-stream"

        logger.debug(f"POST {url}")
        logger.debug(f"Headers: {headers}")
        logger.debug(f"Data: {json.dumps(data, indent=2)}")

        response = self.client.post(
            url,
            json=data,
            headers=headers,
            timeout=self.timeout if not stream else None,
        )

        logger.debug(f"Response status: {response.status_code}")
        return response

    def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> httpx.Response:
        """Send GET request.

        Args:
            endpoint: API endpoint
            params: Query parameters

        Returns:
            HTTP response object
        """
        url = self._build_url(endpoint)
        logger.debug(f"GET {url}")

        response = self.client.get(
            url,
            params=params,
            headers=self.headers,
        )

        logger.debug(f"Response status: {response.status_code}")
        return response

    def delete(self, endpoint: str) -> httpx.Response:
        """Send DELETE request.

        Args:
            endpoint: API endpoint

        Returns:
            HTTP response object
        """
        url = self._build_url(endpoint)
        logger.debug(f"DELETE {url}")

        response = self.client.delete(
            url,
            headers=self.headers,
        )

        logger.debug(f"Response status: {response.status_code}")
        return response

    def stream_sse(
        self,
        endpoint: str,
        data: Dict[str, Any],
        timeout: int = 60,
    ) -> Iterator[Dict[str, Any]]:
        """Stream Server-Sent Events.

        Args:
            endpoint: API endpoint
            data: JSON payload
            timeout: Streaming timeout in seconds

        Yields:
            Parsed SSE events as dictionaries

        Raises:
            TimeoutError: If streaming exceeds timeout
            ValueError: If event parsing fails
        """
        url = self._build_url(endpoint)
        headers = self.headers.copy()
        headers["Accept"] = "text/event-stream"

        logger.debug(f"Streaming POST {url}")

        with httpx.stream(
            "POST",
            url,
            json=data,
            headers=headers,
            timeout=timeout,
        ) as response:
            response.raise_for_status()

            client = sseclient.SSEClient(response)

            for event in client.events():
                # Skip comments and empty events
                if not event.data or event.data.startswith(":"):
                    continue

                # Check for [DONE] marker
                if event.data.strip() == "[DONE]":
                    logger.debug("Received [DONE] marker")
                    break

                try:
                    # Parse JSON data
                    event_data = json.loads(event.data)
                    logger.debug(f"Received event: {event_data.get('type', 'unknown')}")
                    yield event_data
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse SSE event: {event.data[:100]}")
                    raise ValueError(f"Invalid SSE event JSON: {e}")

    def close(self):
        """Close HTTP client."""
        self.client.close()
        logger.info("API Client closed")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


class APIError(Exception):
    """Base exception for API errors."""

    def __init__(self, message: str, status_code: Optional[int] = None, response: Optional[Dict] = None):
        self.message = message
        self.status_code = status_code
        self.response = response
        super().__init__(self.message)


class EndpointNotFoundError(APIError):
    """Raised when endpoint returns 404."""

    pass


class AuthenticationError(APIError):
    """Raised when authentication fails."""

    pass


class ServerError(APIError):
    """Raised on 5xx server errors."""

    pass
