"""
Validators - Validation utilities for API responses and events
"""

import logging
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


def validate_response_structure(
    response_data: Dict[str, Any],
    required_fields: Optional[List[str]] = None,
) -> tuple[bool, List[str]]:
    """Validate response structure.

    Args:
        response_data: Response dictionary
        required_fields: List of required field names

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []

    if not isinstance(response_data, dict):
        errors.append(f"Response must be a dictionary, got {type(response_data)}")
        return False, errors

    # Check required fields
    if required_fields:
        for field in required_fields:
            if field not in response_data:
                errors.append(f"Missing required field: {field}")

    # Check common response structure
    if "id" in response_data:
        if not isinstance(response_data["id"], str):
            errors.append(f"'id' must be string, got {type(response_data['id'])}")
        if not response_data["id"].startswith("resp_"):
            errors.append(f"'id' must start with 'resp_', got {response_data['id']}")

    if "object" in response_data:
        if response_data["object"] != "response":
            errors.append(f"'object' must be 'response', got {response_data['object']}")

    if "status" in response_data:
        valid_statuses = ["queued", "in_progress", "completed", "failed", "cancelled", "incomplete"]
        if response_data["status"] not in valid_statuses:
            errors.append(f"Invalid status: {response_data['status']}")

    return len(errors) == 0, errors


def validate_event_structure(
    event_data: Dict[str, Any],
    event_type: str,
    required_fields: Optional[List[str]] = None,
) -> tuple[bool, List[str]]:
    """Validate SSE event structure.

    Args:
        event_data: Event dictionary
        event_type: Expected event type
        required_fields: List of required field names

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []

    if not isinstance(event_data, dict):
        errors.append(f"Event must be a dictionary, got {type(event_data)}")
        return False, errors

    # Check type field
    if "type" not in event_data:
        errors.append("Missing required field: type")
    elif event_data["type"] != event_type:
        errors.append(f"Expected type '{event_type}', got '{event_data['type']}'")

    # Check sequence_number
    if "sequence_number" not in event_data:
        errors.append("Missing required field: sequence_number")
    elif not isinstance(event_data["sequence_number"], int):
        errors.append(f"sequence_number must be int, got {type(event_data['sequence_number'])}")

    # Check required fields
    if required_fields:
        for field in required_fields:
            if field not in event_data:
                errors.append(f"Missing required field: {field}")

    return len(errors) == 0, errors


def validate_parameter_type(
    param_name: str,
    param_value: Any,
    expected_type: str,
) -> tuple[bool, Optional[str]]:
    """Validate parameter type.

    Args:
        param_name: Parameter name
        param_value: Parameter value
        expected_type: Expected type string (e.g., "string", "integer", "boolean")

    Returns:
        Tuple of (is_valid, error_message)
    """
    type_map = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "array": list,
        "object": dict,
        "map": dict,
    }

    # Handle union types (e.g., "string | array")
    if "|" in expected_type:
        valid_types = [t.strip() for t in expected_type.split("|")]
        for valid_type in valid_types:
            is_valid, _ = validate_parameter_type(param_name, param_value, valid_type)
            if is_valid:
                return True, None

        return False, f"Parameter '{param_name}' must be one of {valid_types}, got {type(param_value).__name__}"

    # Handle "string or array" cases
    if expected_type not in type_map:
        logger.warning(f"Unknown type '{expected_type}' for parameter '{param_name}'")
        return True, None  # Skip validation for unknown types

    expected_python_type = type_map[expected_type]

    if not isinstance(param_value, expected_python_type):
        return False, f"Parameter '{param_name}' must be {expected_type}, got {type(param_value).__name__}"

    return True, None


def validate_streaming_sequence(events: List[Dict[str, Any]]) -> tuple[bool, List[str]]:
    """Validate streaming event sequence.

    Args:
        events: List of events in order received

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []

    if not events:
        errors.append("No events received")
        return False, errors

    # Check sequence numbers are monotonically increasing
    prev_seq = -1
    for i, event in enumerate(events):
        seq = event.get("sequence_number", -1)
        if seq <= prev_seq:
            errors.append(f"Event {i}: sequence_number {seq} not greater than previous {prev_seq}")
        prev_seq = seq

    # Check first event is response.created
    if events[0].get("type") != "response.created":
        errors.append(f"First event must be 'response.created', got '{events[0].get('type')}'")

    # Check last event is response.completed or response.failed
    valid_final_events = ["response.completed", "response.failed", "response.incomplete"]
    if events[-1].get("type") not in valid_final_events:
        errors.append(f"Last event must be completion event, got '{events[-1].get('type')}'")

    # Check for critical events
    event_types = {event.get("type") for event in events}
    if "response.output_item.added" in event_types:
        if "response.output_item.done" not in event_types:
            errors.append("Missing 'response.output_item.done' event")

    return len(errors) == 0, errors


def validate_delta_format(delta: Any, event_type: str) -> tuple[bool, Optional[str]]:
    """Validate delta field format.

    According to OpenAI spec, delta should be a string, not an object.

    Args:
        delta: Delta value
        event_type: Event type

    Returns:
        Tuple of (is_valid, error_message)
    """
    # For most delta events, delta should be a string
    if event_type in [
        "response.output_text.delta",
        "response.reasoning_text.delta",
        "response.reasoning_summary_text.delta",
        "response.refusal.delta",
        "response.function_call_arguments.delta",
        "response.code_interpreter_call_code.delta",
    ]:
        if not isinstance(delta, str):
            return False, f"Delta must be string for {event_type}, got {type(delta).__name__}"

    return True, None


def validate_response_id_format(response_id: str) -> tuple[bool, Optional[str]]:
    """Validate response ID format.

    Args:
        response_id: Response ID

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(response_id, str):
        return False, f"Response ID must be string, got {type(response_id).__name__}"

    if not response_id.startswith("resp_"):
        return False, f"Response ID must start with 'resp_', got '{response_id}'"

    if len(response_id) < 10:
        return False, f"Response ID seems too short: '{response_id}'"

    return True, None


def compare_event_counts(
    received_events: List[Dict[str, Any]],
    expected_events: Set[str],
) -> Dict[str, Any]:
    """Compare received events with expected events.

    Args:
        received_events: List of received events
        expected_events: Set of expected event types

    Returns:
        Dictionary with comparison results
    """
    received_types = {event.get("type") for event in received_events}

    return {
        "total_received": len(received_events),
        "unique_types": len(received_types),
        "missing_events": expected_events - received_types,
        "unexpected_events": received_types - expected_events,
        "event_counts": {
            event_type: sum(1 for e in received_events if e.get("type") == event_type)
            for event_type in received_types
        },
    }
