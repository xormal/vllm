"""
Spec Loader - Load and parse SPEC_TO_CODE_MAPPING.json
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SpecLoader:
    """Loader for OpenAI Responses API specification mapping."""

    def __init__(self, spec_file: str = "../SPEC_TO_CODE_MAPPING.json"):
        """Initialize spec loader.

        Args:
            spec_file: Path to SPEC_TO_CODE_MAPPING.json (relative to cwd or absolute)
        """
        self.spec_file = Path(spec_file)
        self.spec_data: Optional[Dict[str, Any]] = None
        self.load()

    def load(self) -> Dict[str, Any]:
        """Load spec mapping file.

        Returns:
            Spec mapping dictionary

        Raises:
            FileNotFoundError: If spec file not found
            json.JSONDecodeError: If spec file is not valid JSON
        """
        if not self.spec_file.exists():
            raise FileNotFoundError(f"Spec file not found: {self.spec_file}")

        try:
            with open(self.spec_file, "r", encoding="utf-8") as f:
                self.spec_data = json.load(f)

            logger.info(f"Loaded spec from {self.spec_file}")
            logger.info(f"Spec version: {self.spec_data.get('version', 'unknown')}")

            return self.spec_data
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse spec file: {e}")
            raise

    def get_endpoints(self) -> Dict[str, Dict[str, Any]]:
        """Get all endpoint definitions.

        Returns:
            Dictionary of endpoints
        """
        if not self.spec_data:
            self.load()

        return self.spec_data.get("endpoints", {})

    def get_endpoint(self, endpoint: str) -> Optional[Dict[str, Any]]:
        """Get specific endpoint definition.

        Args:
            endpoint: Endpoint path (e.g., "POST /v1/responses")

        Returns:
            Endpoint definition or None if not found
        """
        endpoints = self.get_endpoints()
        return endpoints.get(endpoint)

    def get_implemented_endpoints(self) -> List[str]:
        """Get list of implemented endpoints.

        Returns:
            List of endpoint paths
        """
        endpoints = self.get_endpoints()
        return [ep for ep, info in endpoints.items() if info.get("implemented", False)]

    def get_request_parameters(self, model: str = "ResponsesRequest") -> Dict[str, Dict[str, Any]]:
        """Get request parameter definitions.

        Args:
            model: Request model name (default: ResponsesRequest)

        Returns:
            Dictionary of parameters
        """
        if not self.spec_data:
            self.load()

        return self.spec_data.get("request_parameters", {}).get(model, {})

    def get_parameter(self, param_name: str, model: str = "ResponsesRequest") -> Optional[Dict[str, Any]]:
        """Get specific parameter definition.

        Args:
            param_name: Parameter name
            model: Request model name

        Returns:
            Parameter definition or None if not found
        """
        params = self.get_request_parameters(model)
        return params.get(param_name)

    def get_streaming_events(self) -> Dict[str, Dict[str, Any]]:
        """Get all streaming event definitions.

        Returns:
            Dictionary of events
        """
        if not self.spec_data:
            self.load()

        return self.spec_data.get("streaming_events", {})

    def get_event(self, event_type: str) -> Optional[Dict[str, Any]]:
        """Get specific event definition.

        Args:
            event_type: Event type (e.g., "response.created")

        Returns:
            Event definition or None if not found
        """
        events = self.get_streaming_events()
        return events.get(event_type)

    def get_implemented_events(self) -> List[str]:
        """Get list of implemented streaming events.

        Returns:
            List of event types
        """
        events = self.get_streaming_events()
        return [evt for evt, info in events.items() if info.get("implemented", False)]

    def get_critical_endpoints(self) -> List[str]:
        """Get list of critical endpoints.

        Returns:
            List of critical endpoint paths
        """
        endpoints = self.get_endpoints()
        return [
            ep
            for ep, info in endpoints.items()
            if info.get("test_priority") == "critical" and info.get("implemented", False)
        ]

    def get_critical_events(self) -> List[str]:
        """Get list of critical streaming events.

        Returns:
            List of critical event types
        """
        events = self.get_streaming_events()
        return [
            evt
            for evt, info in events.items()
            if info.get("test_priority") == "critical" and info.get("implemented", False)
        ]

    def get_summary(self) -> Dict[str, Any]:
        """Get compliance summary.

        Returns:
            Summary dictionary
        """
        if not self.spec_data:
            self.load()

        return self.spec_data.get("summary", {})

    def get_overall_compliance_score(self) -> int:
        """Get overall compliance score.

        Returns:
            Compliance score (0-100)
        """
        summary = self.get_summary()
        return summary.get("overall_compliance_score", 0)

    def get_missing_features(self) -> Dict[str, List[str]]:
        """Get lists of missing features by priority.

        Returns:
            Dictionary with 'critical', 'high', 'medium', 'low' keys
        """
        summary = self.get_summary()

        return {
            "critical": summary.get("critical_missing", []),
            "high": summary.get("high_priority_missing", []),
            "medium": [],
            "low": [],
        }

    def validate_spec(self) -> bool:
        """Validate spec mapping structure.

        Returns:
            True if spec is valid, False otherwise
        """
        if not self.spec_data:
            return False

        required_keys = ["version", "endpoints", "request_parameters", "streaming_events", "summary"]

        for key in required_keys:
            if key not in self.spec_data:
                logger.error(f"Missing required key in spec: {key}")
                return False

        return True

    def get_test_values(self, param_name: str, model: str = "ResponsesRequest") -> List[Any]:
        """Get test values for a parameter.

        Args:
            param_name: Parameter name
            model: Request model name

        Returns:
            List of test values
        """
        param = self.get_parameter(param_name, model)
        if not param:
            return []

        return param.get("test_values", [])

    def get_required_fields(self, event_type: str) -> List[str]:
        """Get required fields for an event.

        Args:
            event_type: Event type

        Returns:
            List of required field names
        """
        event = self.get_event(event_type)
        if not event:
            return []

        return event.get("required_fields", [])
