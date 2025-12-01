"""
Streaming Checker - Tests SSE streaming events
"""

import logging
from typing import Dict, List

from utils.api_client import APIClient
from utils.spec_loader import SpecLoader
from utils.validators import (
    validate_event_structure,
    validate_streaming_sequence,
    validate_delta_format,
    compare_event_counts,
)

logger = logging.getLogger(__name__)


class StreamingChecker:
    """Checker for Responses API streaming events."""

    def __init__(self, client: APIClient, spec: SpecLoader):
        """Initialize streaming checker.

        Args:
            client: API client instance
            spec: Spec loader instance
        """
        self.client = client
        self.spec = spec
        self.results = {}

    def check_streaming(self) -> Dict:
        """Check streaming functionality.

        Returns:
            Dictionary with test results
        """
        logger.info("Starting streaming checks...")

        results = {
            "basic_streaming": self._test_basic_streaming(),
            "event_validation": self._test_event_validation(),
            "reasoning_streaming": self._test_reasoning_streaming(),
            "sequence_validation": None,  # Will be filled by basic_streaming
        }

        # Calculate summary
        total_tests = len([r for r in results.values() if r is not None])
        passed_tests = len([r for r in results.values() if r and r.get("status") == "passed"])

        results["summary"] = {
            "total": total_tests,
            "passed": passed_tests,
            "failed": total_tests - passed_tests,
            "pass_rate": (passed_tests / total_tests * 100) if total_tests > 0 else 0,
        }

        logger.info(f"Streaming checks complete: {passed_tests}/{total_tests} passed")
        return results

    def _test_basic_streaming(self) -> Dict:
        """Test basic streaming functionality.

        Returns:
            Test result dictionary
        """
        logger.info("Testing basic streaming...")

        try:
            data = {
                "model": "gpt-4o-mini",
                "input": "Count from 1 to 5",
                "max_output_tokens": 50,
                "stream": True,
            }

            events = []
            for event in self.client.stream_sse("/v1/responses", data, timeout=60):
                events.append(event)

            if not events:
                return {
                    "status": "failed",
                    "error": "No events received",
                }

            # Validate event sequence
            is_valid, errors = validate_streaming_sequence(events)

            # Check for critical events
            event_types = {event.get("type") for event in events}
            critical_events = self.spec.get_critical_events()

            missing_critical = set(critical_events) - event_types

            # Compare with expected events
            comparison = compare_event_counts(
                events,
                set(self.spec.get_implemented_events()),
            )

            result = {
                "status": "passed" if is_valid and not missing_critical else "failed",
                "total_events": len(events),
                "unique_event_types": len(event_types),
                "event_types": list(event_types),
                "missing_critical_events": list(missing_critical),
                "sequence_valid": is_valid,
                "sequence_errors": errors if not is_valid else [],
                "event_comparison": comparison,
            }

            # Store for sequence validation
            self.results["sequence_validation"] = {
                "status": "passed" if is_valid else "failed",
                "errors": errors,
            }

            return result

        except TimeoutError:
            return {
                "status": "failed",
                "error": "Streaming timeout",
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
            }

    def _test_event_validation(self) -> Dict:
        """Test event structure validation.

        Returns:
            Test result dictionary
        """
        logger.info("Testing event structure validation...")

        try:
            data = {
                "model": "gpt-4o-mini",
                "input": "Say hello",
                "max_output_tokens": 20,
                "stream": True,
            }

            events = []
            validation_results = {}

            for event in self.client.stream_sse("/v1/responses", data, timeout=30):
                events.append(event)
                event_type = event.get("type")

                # Get required fields for this event type
                event_spec = self.spec.get_event(event_type)
                if not event_spec:
                    logger.warning(f"Unknown event type: {event_type}")
                    continue

                required_fields = event_spec.get("required_fields", [])

                # Validate event structure
                is_valid, errors = validate_event_structure(
                    event,
                    event_type,
                    required_fields,
                )

                if event_type not in validation_results:
                    validation_results[event_type] = {
                        "count": 0,
                        "valid": 0,
                        "errors": [],
                    }

                validation_results[event_type]["count"] += 1
                if is_valid:
                    validation_results[event_type]["valid"] += 1
                else:
                    validation_results[event_type]["errors"].extend(errors)

                # Check delta format for delta events
                if "delta" in event:
                    is_valid, error = validate_delta_format(event["delta"], event_type)
                    if not is_valid:
                        validation_results[event_type]["errors"].append(error)

            # Calculate pass rate
            total_events = len(events)
            valid_events = sum(r["valid"] for r in validation_results.values())

            return {
                "status": "passed" if valid_events == total_events else "failed",
                "total_events": total_events,
                "valid_events": valid_events,
                "pass_rate": (valid_events / total_events * 100) if total_events > 0 else 0,
                "event_validation": validation_results,
            }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
            }

    def _test_reasoning_streaming(self) -> Dict:
        """Test reasoning model streaming events.

        Returns:
            Test result dictionary
        """
        logger.info("Testing reasoning streaming...")

        try:
            data = {
                "model": "gpt-4o-mini",
                "input": "Explain step by step: what is 2+2?",
                "max_output_tokens": 100,
                "stream": True,
                "reasoning": {"effort": "medium"},
            }

            events = []
            reasoning_events = []

            for event in self.client.stream_sse("/v1/responses", data, timeout=60):
                events.append(event)
                event_type = event.get("type")

                # Collect reasoning-related events
                if "reasoning" in event_type:
                    reasoning_events.append(event)

            # Check for reasoning events
            reasoning_event_types = {e.get("type") for e in reasoning_events}

            expected_reasoning_events = {
                "response.reasoning_text.delta",
                "response.reasoning_text.done",
            }

            found_reasoning_events = reasoning_event_types & expected_reasoning_events

            result = {
                "status": "passed" if found_reasoning_events else "skipped",
                "total_events": len(events),
                "reasoning_events_count": len(reasoning_events),
                "reasoning_event_types": list(reasoning_event_types),
                "found_expected_events": list(found_reasoning_events),
            }

            if not found_reasoning_events:
                result["note"] = "No reasoning events found - model may not support reasoning"

            # Check delta format for reasoning events
            delta_errors = []
            for event in reasoning_events:
                if "delta" in event:
                    is_valid, error = validate_delta_format(event["delta"], event["type"])
                    if not is_valid:
                        delta_errors.append(error)

            if delta_errors:
                result["status"] = "failed"
                result["delta_errors"] = delta_errors

            return result

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
            }

    def check_specific_event(self, event_type: str) -> Dict:
        """Check a specific event type.

        Args:
            event_type: Event type to check (e.g., "response.created")

        Returns:
            Test result dictionary
        """
        logger.info(f"Checking event: {event_type}")

        event_spec = self.spec.get_event(event_type)
        if not event_spec:
            return {
                "status": "error",
                "error": f"Unknown event type: {event_type}",
            }

        if not event_spec.get("implemented", False):
            return {
                "status": "skipped",
                "reason": "Not implemented in vLLM",
            }

        # Create appropriate request to trigger this event
        try:
            data = {
                "model": "gpt-4o-mini",
                "input": "Test input",
                "max_output_tokens": 20,
                "stream": True,
            }

            found = False
            event_data = None

            for event in self.client.stream_sse("/v1/responses", data, timeout=30):
                if event.get("type") == event_type:
                    found = True
                    event_data = event
                    break

            if not found:
                return {
                    "status": "failed",
                    "error": f"Event {event_type} not received",
                }

            # Validate event structure
            required_fields = event_spec.get("required_fields", [])
            is_valid, errors = validate_event_structure(
                event_data,
                event_type,
                required_fields,
            )

            return {
                "status": "passed" if is_valid else "failed",
                "event_received": True,
                "validation_errors": errors if not is_valid else [],
                "event_data": event_data,
            }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
            }
