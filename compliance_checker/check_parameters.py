"""
Parameter Checker - Tests request/response parameters
"""

import logging
from typing import Any, Dict, List

from utils.api_client import APIClient
from utils.spec_loader import SpecLoader
from utils.validators import validate_parameter_type

logger = logging.getLogger(__name__)


class ParameterChecker:
    """Checker for request/response parameters."""

    def __init__(self, client: APIClient, spec: SpecLoader):
        """Initialize parameter checker.

        Args:
            client: API client instance
            spec: Spec loader instance
        """
        self.client = client
        self.spec = spec
        self.results = {}

    def check_all_parameters(self) -> Dict:
        """Check all request parameters.

        Returns:
            Dictionary with test results
        """
        logger.info("Starting parameter checks...")

        parameters = self.spec.get_request_parameters()
        total = len(parameters)
        tested = 0
        passed = 0
        failed = 0
        skipped = 0

        for param_name, param_info in parameters.items():
            if not param_info.get("implemented", True):
                logger.info(f"⏭️  Skipping {param_name} (not implemented)")
                skipped += 1
                self.results[param_name] = {
                    "status": "skipped",
                    "reason": "not_implemented",
                }
                continue

            logger.info(f"Testing parameter: {param_name}")

            try:
                result = self._test_parameter(param_name, param_info)
                self.results[param_name] = result
                tested += 1

                if result["status"] == "passed":
                    passed += 1
                    logger.info(f"✅ {param_name} passed")
                else:
                    failed += 1
                    logger.error(f"❌ {param_name} failed: {result.get('error', 'unknown')}")

            except Exception as e:
                logger.error(f"❌ {param_name} error: {e}")
                failed += 1
                self.results[param_name] = {
                    "status": "error",
                    "error": str(e),
                }

        summary = {
            "total": total,
            "tested": tested,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "pass_rate": (passed / tested * 100) if tested > 0 else 0,
            "results": self.results,
        }

        logger.info(f"Parameter checks complete: {passed}/{tested} passed")
        return summary

    def _test_parameter(self, param_name: str, param_info: Dict) -> Dict:
        """Test a single parameter.

        Args:
            param_name: Parameter name
            param_info: Parameter information from spec

        Returns:
            Test result dictionary
        """
        test_values = param_info.get("test_values", [])
        param_type = param_info.get("type")
        required = param_info.get("required", False)

        if not test_values:
            # Generate default test value based on type
            test_values = [self._get_default_value(param_type)]

        results = []

        for test_value in test_values:
            result = self._test_parameter_value(
                param_name,
                test_value,
                param_type,
            )
            results.append(result)

        # Check if all tests passed
        all_passed = all(r["status"] == "passed" for r in results)

        return {
            "status": "passed" if all_passed else "failed",
            "param_type": param_type,
            "required": required,
            "test_count": len(results),
            "test_results": results,
        }

    def _test_parameter_value(
        self,
        param_name: str,
        param_value: Any,
        param_type: str,
    ) -> Dict:
        """Test a parameter with a specific value.

        Args:
            param_name: Parameter name
            param_value: Value to test
            param_type: Expected parameter type

        Returns:
            Test result dictionary
        """
        try:
            # Build request data with this parameter
            data = {
                "model": "gpt-4o-mini",
                "input": "Test",
                "max_output_tokens": 20,
                param_name: param_value,
            }

            # Send request
            response = self.client.post("/v1/responses", data=data)

            # Check if request was accepted
            if response.status_code not in [200, 202]:
                # Check if error is due to parameter validation
                try:
                    error_data = response.json()
                    error_message = error_data.get("error", {}).get("message", "")

                    return {
                        "status": "failed",
                        "error": f"Request rejected: {error_message}",
                        "status_code": response.status_code,
                        "test_value": param_value,
                    }
                except:
                    return {
                        "status": "failed",
                        "error": f"HTTP {response.status_code}",
                        "status_code": response.status_code,
                        "test_value": param_value,
                    }

            # Validate type
            is_valid, error = validate_parameter_type(
                param_name,
                param_value,
                param_type,
            )

            if not is_valid:
                return {
                    "status": "failed",
                    "error": error,
                    "test_value": param_value,
                }

            # If we got a response, check if parameter was honored
            response_data = response.json()

            # For some parameters, we can verify they were applied
            verification = self._verify_parameter_applied(
                param_name,
                param_value,
                response_data,
            )

            return {
                "status": "passed",
                "test_value": param_value,
                "verification": verification,
            }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "test_value": param_value,
            }

    def _verify_parameter_applied(
        self,
        param_name: str,
        param_value: Any,
        response_data: Dict,
    ) -> Dict:
        """Verify that parameter was applied in response.

        Args:
            param_name: Parameter name
            param_value: Parameter value
            response_data: Response data

        Returns:
            Verification result dictionary
        """
        verifications = {
            "verified": False,
            "message": "No verification implemented",
        }

        # Verify specific parameters
        if param_name == "max_output_tokens":
            # Check usage
            if "usage" in response_data:
                output_tokens = response_data["usage"].get("output_tokens", 0)
                if output_tokens <= param_value:
                    verifications = {
                        "verified": True,
                        "message": f"Output tokens ({output_tokens}) within limit ({param_value})",
                    }
                else:
                    verifications = {
                        "verified": False,
                        "message": f"Output tokens ({output_tokens}) exceeded limit ({param_value})",
                    }

        elif param_name == "store":
            # Check if response has ID (stored)
            if param_value and "id" in response_data:
                verifications = {
                    "verified": True,
                    "message": "Response stored with ID",
                }
            elif not param_value:
                verifications = {
                    "verified": True,
                    "message": "Store parameter honored",
                }

        elif param_name == "stream":
            # Streaming is tested separately
            verifications = {
                "verified": True,
                "message": "Tested separately",
            }

        elif param_name == "temperature":
            # Check if temperature is in response
            if "temperature" in response_data:
                if response_data["temperature"] == param_value:
                    verifications = {
                        "verified": True,
                        "message": f"Temperature matches ({param_value})",
                    }

        elif param_name == "model":
            # Check if model is in response
            if "model" in response_data:
                # Model name might include version
                if param_value in response_data["model"]:
                    verifications = {
                        "verified": True,
                        "message": f"Model matches ({response_data['model']})",
                    }

        return verifications

    def _get_default_value(self, param_type: str) -> Any:
        """Get default test value for a type.

        Args:
            param_type: Parameter type

        Returns:
            Default value for that type
        """
        defaults = {
            "string": "test",
            "integer": 10,
            "number": 0.5,
            "boolean": True,
            "array": [],
            "object": {},
            "map": {},
        }

        # Handle union types
        if "|" in param_type:
            first_type = param_type.split("|")[0].strip()
            return defaults.get(first_type, None)

        return defaults.get(param_type, None)

    def check_required_parameters(self) -> Dict:
        """Check that required parameters are enforced.

        Returns:
            Test result dictionary
        """
        logger.info("Checking required parameters...")

        # Try to create response without required parameters
        try:
            # Send request with minimal data
            data = {"input": "Test"}  # Missing model

            response = self.client.post("/v1/responses", data=data)

            # Should fail with 400 or 422
            if response.status_code in [400, 422]:
                return {
                    "status": "passed",
                    "message": "Required parameter validation working",
                }
            else:
                return {
                    "status": "failed",
                    "error": f"Expected 400/422, got {response.status_code}",
                }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
            }
