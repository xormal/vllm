"""
Endpoint Checker - Tests all Responses API endpoints
"""

import logging
from typing import Dict, List, Tuple

from utils.api_client import APIClient, APIError
from utils.spec_loader import SpecLoader
from utils.validators import validate_response_structure, validate_response_id_format

logger = logging.getLogger(__name__)


class EndpointChecker:
    """Checker for Responses API endpoints."""

    def __init__(self, client: APIClient, spec: SpecLoader):
        """Initialize endpoint checker.

        Args:
            client: API client instance
            spec: Spec loader instance
        """
        self.client = client
        self.spec = spec
        self.results = {}

    def check_all_endpoints(self) -> Dict[str, any]:
        """Check all endpoints defined in spec.

        Returns:
            Dictionary with test results
        """
        logger.info("Starting endpoint checks...")

        endpoints = self.spec.get_endpoints()
        total = len(endpoints)
        passed = 0
        failed = 0
        skipped = 0

        for endpoint_path, endpoint_info in endpoints.items():
            if not endpoint_info.get("implemented", False):
                logger.info(f"⏭️  Skipping {endpoint_path} (not implemented)")
                skipped += 1
                self.results[endpoint_path] = {
                    "status": "skipped",
                    "reason": "not_implemented",
                }
                continue

            logger.info(f"Testing {endpoint_path}...")

            try:
                result = self._test_endpoint(endpoint_path, endpoint_info)
                self.results[endpoint_path] = result

                if result["status"] == "passed":
                    logger.info(f"✅ {endpoint_path} passed")
                    passed += 1
                else:
                    logger.error(f"❌ {endpoint_path} failed: {result.get('error', 'unknown')}")
                    failed += 1

            except Exception as e:
                logger.error(f"❌ {endpoint_path} error: {e}")
                failed += 1
                self.results[endpoint_path] = {
                    "status": "error",
                    "error": str(e),
                }

        summary = {
            "total": total,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "pass_rate": (passed / (passed + failed) * 100) if (passed + failed) > 0 else 0,
            "results": self.results,
        }

        logger.info(f"Endpoint checks complete: {passed}/{total} passed")
        return summary

    def _test_endpoint(self, endpoint_path: str, endpoint_info: Dict) -> Dict:
        """Test a single endpoint.

        Args:
            endpoint_path: Endpoint path (e.g., "POST /v1/responses")
            endpoint_info: Endpoint information from spec

        Returns:
            Test result dictionary
        """
        method, path = endpoint_path.split(" ", 1)

        # Choose test method based on endpoint
        if method == "POST" and path == "/v1/responses":
            return self._test_create_response()
        elif method == "GET" and "{response_id}" in path:
            return self._test_retrieve_response()
        elif method == "POST" and "cancel" in path:
            return self._test_cancel_response()
        elif method == "POST" and "tool_outputs" in path:
            return self._test_tool_outputs()
        elif method == "DELETE" and "{response_id}" in path:
            return self._test_delete_response()
        elif method == "GET" and "input_items" in path:
            return self._test_input_items()
        elif method == "POST" and "input_tokens" in path:
            return self._test_input_tokens()
        elif method == "GET" and path == "/v1/models":
            return self._test_models()
        else:
            return {
                "status": "skipped",
                "reason": f"No test implemented for {method} {path}",
            }

    def _test_create_response(self) -> Dict:
        """Test POST /v1/responses endpoint."""
        try:
            data = {
                "model": "gpt-4o-mini",
                "input": "Hello, this is a test.",
                "max_output_tokens": 50,
            }

            response = self.client.post("/v1/responses", data=data)

            if response.status_code != 200:
                return {
                    "status": "failed",
                    "error": f"Expected 200, got {response.status_code}",
                    "response_body": response.text[:500],
                }

            response_data = response.json()

            # Validate structure
            is_valid, errors = validate_response_structure(
                response_data,
                required_fields=["id", "object", "status"],
            )

            if not is_valid:
                return {
                    "status": "failed",
                    "error": "Invalid response structure",
                    "validation_errors": errors,
                }

            # Validate response ID format
            is_valid, error = validate_response_id_format(response_data["id"])
            if not is_valid:
                return {
                    "status": "failed",
                    "error": error,
                }

            return {
                "status": "passed",
                "response_id": response_data["id"],
                "response_status": response_data["status"],
            }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
            }

    def _test_retrieve_response(self) -> Dict:
        """Test GET /v1/responses/{response_id} endpoint."""
        try:
            # First create a response to retrieve
            create_result = self._test_create_response()
            if create_result["status"] != "passed":
                return {
                    "status": "failed",
                    "error": "Failed to create response for retrieval test",
                }

            response_id = create_result["response_id"]

            # Now retrieve it
            response = self.client.get(f"/v1/responses/{response_id}")

            if response.status_code != 200:
                return {
                    "status": "failed",
                    "error": f"Expected 200, got {response.status_code}",
                }

            response_data = response.json()

            # Validate structure
            is_valid, errors = validate_response_structure(
                response_data,
                required_fields=["id", "object", "status"],
            )

            if not is_valid:
                return {
                    "status": "failed",
                    "error": "Invalid response structure",
                    "validation_errors": errors,
                }

            # Check ID matches
            if response_data["id"] != response_id:
                return {
                    "status": "failed",
                    "error": f"Response ID mismatch: expected {response_id}, got {response_data['id']}",
                }

            return {
                "status": "passed",
                "response_id": response_id,
            }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
            }

    def _test_cancel_response(self) -> Dict:
        """Test POST /v1/responses/{response_id}/cancel endpoint."""
        try:
            # Create a background response
            data = {
                "model": "gpt-4o-mini",
                "input": "Generate a long text...",
                "max_output_tokens": 1000,
                "background": True,
            }

            create_response = self.client.post("/v1/responses", data=data)
            if create_response.status_code != 200:
                return {
                    "status": "failed",
                    "error": f"Failed to create background response: {create_response.status_code}",
                }

            response_id = create_response.json()["id"]

            # Try to cancel it
            cancel_response = self.client.post(f"/v1/responses/{response_id}/cancel")

            if cancel_response.status_code not in [200, 202]:
                return {
                    "status": "failed",
                    "error": f"Expected 200/202, got {cancel_response.status_code}",
                }

            return {
                "status": "passed",
                "response_id": response_id,
            }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
            }

    def _test_tool_outputs(self) -> Dict:
        """Test POST /v1/responses/{response_id}/tool_outputs endpoint."""
        return {
            "status": "skipped",
            "reason": "Tool outputs workflow differs in vLLM (uses previous_response_id)",
        }

    def _test_delete_response(self) -> Dict:
        """Test DELETE /v1/responses/{response_id} endpoint."""
        return {
            "status": "skipped",
            "reason": "Not implemented in vLLM",
        }

    def _test_input_items(self) -> Dict:
        """Test GET /v1/responses/{response_id}/input_items endpoint."""
        return {
            "status": "skipped",
            "reason": "Not implemented in vLLM",
        }

    def _test_input_tokens(self) -> Dict:
        """Test POST /v1/responses/input_tokens endpoint."""
        return {
            "status": "skipped",
            "reason": "Not implemented in vLLM",
        }

    def _test_models(self) -> Dict:
        """Test GET /v1/models endpoint."""
        try:
            response = self.client.get("/v1/models")

            if response.status_code != 200:
                return {
                    "status": "failed",
                    "error": f"Expected 200, got {response.status_code}",
                }

            models_data = response.json()

            # Validate structure
            if "data" not in models_data:
                return {
                    "status": "failed",
                    "error": "Missing 'data' field in response",
                }

            if not isinstance(models_data["data"], list):
                return {
                    "status": "failed",
                    "error": "'data' must be an array",
                }

            return {
                "status": "passed",
                "model_count": len(models_data["data"]),
                "models": [m.get("id") for m in models_data["data"]][:5],  # First 5 models
            }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
            }
