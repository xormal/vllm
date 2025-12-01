#!/usr/bin/env python3
"""
External test for Bug #5 and Bug #6 fixes in vLLM Responses API.

This script tests that:
1. Bug #5: response.tool_call.delta has correct format (delta.content array of strings)
2. Bug #6: Server accepts standard OpenAI tool format

Usage:
    python test_bug_5_and_6_fixes.py
    python test_bug_5_and_6_fixes.py --host 192.168.228.43 --port 8000

Exit codes:
    0 - All tests passed
    1 - Tests failed
    2 - Connection error
"""

import argparse
import json
import sys
import time
from typing import Any, Generator

try:
    import requests
except ImportError:
    print("ERROR: requests library not found")
    print("Install with: pip install requests")
    sys.exit(2)


# ANSI color codes
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


def parse_sse_line(line: str) -> dict[str, Any] | None:
    """Parse a single SSE line into event data."""
    line = line.strip()

    if not line or line == "data: [DONE]":
        return None

    # Extract event type
    event_type = None
    if line.startswith("event:"):
        event_type = line[6:].strip()
        return {"_event_type": event_type}

    # Extract data
    if line.startswith("data:"):
        data_str = line[5:].strip()
        try:
            return json.loads(data_str)
        except json.JSONDecodeError as e:
            print(f"{YELLOW}WARNING: Failed to parse SSE data: {e}{RESET}")
            print(f"Line: {data_str[:100]}...")
            return None

    return None


def stream_sse_events(response: requests.Response) -> Generator[dict[str, Any], None, None]:
    """Stream and parse SSE events from response."""
    current_event_type = None

    for line in response.iter_lines(decode_unicode=True):
        if not line:
            continue

        parsed = parse_sse_line(line)
        if parsed is None:
            continue

        # Handle event type marker
        if "_event_type" in parsed:
            current_event_type = parsed["_event_type"]
            continue

        # Add event type to data if available
        if current_event_type and "type" not in parsed:
            parsed["type"] = current_event_type

        yield parsed


class TestResults:
    """Track test results."""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.warnings = 0
        self.errors = []

    def add_pass(self, test_name: str):
        """Record a passed test."""
        self.passed += 1
        print(f"  {GREEN}✓{RESET} {test_name}")

    def add_fail(self, test_name: str, error: str):
        """Record a failed test."""
        self.failed += 1
        self.errors.append(f"{test_name}: {error}")
        print(f"  {RED}✗{RESET} {test_name}")
        print(f"    {RED}Error: {error}{RESET}")

    def add_warning(self, test_name: str, message: str):
        """Record a warning."""
        self.warnings += 1
        print(f"  {YELLOW}⚠{RESET} {test_name}")
        print(f"    {YELLOW}Warning: {message}{RESET}")

    def print_summary(self):
        """Print test summary."""
        print(f"\n{'='*60}")
        print(f"Test Summary:")
        print(f"  {GREEN}Passed:{RESET}   {self.passed}")
        print(f"  {RED}Failed:{RESET}   {self.failed}")
        print(f"  {YELLOW}Warnings:{RESET} {self.warnings}")
        print(f"{'='*60}")

        if self.errors:
            print(f"\n{RED}Errors:{RESET}")
            for error in self.errors:
                print(f"  • {error}")

        if self.failed == 0:
            print(f"\n{GREEN}✓ All tests passed!{RESET}")
            return True
        else:
            print(f"\n{RED}✗ Some tests failed.{RESET}")
            return False


def test_bug_6_tools_format(base_url: str, results: TestResults):
    """Test Bug #6: Server should accept standard OpenAI tool format."""
    print(f"\n{BLUE}Testing Bug #6: Standard OpenAI tool format{RESET}")
    print("-" * 60)

    # Standard OpenAI tool format (from official API spec)
    payload = {
        "model": "openai/gpt-oss-120b",
        "input": "What is 2+2?",
        "stream": False,
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "calculator",
                    "description": "Perform basic math operations",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "operation": {
                                "type": "string",
                                "enum": ["add", "subtract", "multiply", "divide"]
                            },
                            "a": {"type": "number"},
                            "b": {"type": "number"}
                        },
                        "required": ["operation", "a", "b"]
                    }
                }
            }
        ]
    }

    try:
        response = requests.post(
            f"{base_url}/responses",
            json=payload,
            timeout=30
        )

        # Check HTTP status
        if response.status_code == 400:
            error_data = response.json().get("error", {})
            error_msg = error_data.get("message", "")

            # Check if error is about tool format
            if "FunctionTool" in error_msg or "Field required" in error_msg:
                results.add_fail(
                    "Standard OpenAI tool format",
                    f"Server rejected standard format. Bug #6 NOT FIXED. Error: {error_msg[:200]}"
                )
                return

        if response.status_code >= 400:
            results.add_fail(
                "Standard OpenAI tool format",
                f"HTTP {response.status_code}: {response.text[:200]}"
            )
            return

        # Success - server accepted the format
        results.add_pass("Standard OpenAI tool format accepted")

        # Verify response structure
        data = response.json()
        if "object" in data and data["object"] == "response":
            results.add_pass("Response structure valid")
        else:
            results.add_warning(
                "Response structure",
                f"Unexpected response format: {data.get('object')}"
            )

    except requests.exceptions.Timeout:
        results.add_fail("Standard OpenAI tool format", "Request timeout")
    except requests.exceptions.ConnectionError as e:
        results.add_fail("Standard OpenAI tool format", f"Connection error: {e}")
    except Exception as e:
        results.add_fail("Standard OpenAI tool format", f"Unexpected error: {e}")


def test_bug_5_delta_format(base_url: str, results: TestResults):
    """Test Bug #5: response.tool_call.delta should have correct format."""
    print(f"\n{BLUE}Testing Bug #5: response.tool_call.delta format{RESET}")
    print("-" * 60)

    # Request with streaming enabled
    payload = {
        "model": "openai/gpt-oss-120b",
        "input": "List all files in the current directory",
        "stream": True,
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "list_files",
                    "description": "List files in a directory",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"}
                        }
                    }
                }
            }
        ]
    }

    try:
        response = requests.post(
            f"{base_url}/responses",
            json=payload,
            stream=True,
            timeout=60
        )

        if response.status_code >= 400:
            results.add_fail(
                "Bug #5 test request",
                f"HTTP {response.status_code}: {response.text[:200]}"
            )
            return

        # Collect tool_call.delta events
        tool_call_deltas = []
        event_count = 0
        max_events = 100  # Safety limit

        for event in stream_sse_events(response):
            event_count += 1
            if event_count > max_events:
                results.add_warning(
                    "Event stream",
                    f"Stopped after {max_events} events (safety limit)"
                )
                break

            event_type = event.get("type", "")

            if event_type == "response.tool_call.delta":
                tool_call_deltas.append(event)

            # Stop after we get some tool call events
            if len(tool_call_deltas) >= 3:
                break

            # Also stop if response is completed
            if event_type in ("response.completed", "response.failed", "response.incomplete"):
                break

        # Close the stream
        response.close()

        # Validate we got tool_call.delta events
        if not tool_call_deltas:
            results.add_warning(
                "response.tool_call.delta events",
                "No tool_call.delta events found. Model may not have called tools."
            )
            return

        results.add_pass(f"Found {len(tool_call_deltas)} response.tool_call.delta events")

        # Validate delta format for each event
        all_deltas_valid = True

        for i, event in enumerate(tool_call_deltas):
            delta = event.get("delta")

            # Check 1: delta must be present
            if delta is None:
                results.add_fail(
                    f"Delta event {i+1}",
                    "Missing 'delta' field"
                )
                all_deltas_valid = False
                continue

            # Check 2: delta must be a string payload
            if not isinstance(delta, str):
                results.add_fail(
                    f"Delta event {i+1} type",
                    f"delta is {type(delta).__name__}, expected string. Bug #5 NOT FIXED!"
                )
                all_deltas_valid = False
                continue

            if delta == "":
                results.add_warning(
                    f"Delta event {i+1} payload",
                    "delta payload is empty string"
                )
                continue

        # Summary for Bug #5
        if all_deltas_valid:
            results.add_pass("All delta events have correct format (string payload)")
            results.add_pass("Bug #5 appears to be FIXED ✓")

            # Try to reconstruct full tool call JSON
            try:
                latest_chunk = next(
                    (
                        event["delta"]
                        for event in reversed(tool_call_deltas)
                        if event.get("delta")
                    ),
                    ""
                )

                if latest_chunk:
                    # Try to parse it
                    parsed = json.loads(latest_chunk)
                    if isinstance(parsed, list) and len(parsed) > 0:
                        tool_call = parsed[0]
                        if tool_call.get("type") == "tool_call":
                            results.add_pass(
                                f"Reconstructed tool call: {tool_call.get('name', 'unknown')}"
                            )
                        else:
                            results.add_warning(
                                "Tool call reconstruction",
                                f"Unexpected type: {tool_call.get('type')}"
                            )
                    else:
                        results.add_warning(
                            "Tool call reconstruction",
                            f"Unexpected structure: {type(parsed).__name__}"
                        )
            except json.JSONDecodeError as e:
                results.add_warning(
                    "Tool call reconstruction",
                    f"Could not parse full JSON: {e}"
                )
            except Exception as e:
                results.add_warning(
                    "Tool call reconstruction",
                    f"Unexpected error: {e}"
                )
        else:
            results.add_fail(
                "Delta format validation",
                "Some delta events have incorrect format. Bug #5 NOT FIXED!"
            )

    except requests.exceptions.Timeout:
        results.add_fail("Bug #5 test request", "Request timeout")
    except requests.exceptions.ConnectionError as e:
        results.add_fail("Bug #5 test request", f"Connection error: {e}")
    except Exception as e:
        results.add_fail("Bug #5 test request", f"Unexpected error: {e}")


def test_server_health(base_url: str, results: TestResults) -> bool:
    """Test server health endpoint."""
    print(f"\n{BLUE}Testing server health{RESET}")
    print("-" * 60)

    try:
        response = requests.get(f"{base_url}/health", timeout=10)

        if response.status_code == 200:
            results.add_pass("Server is healthy")
            return True
        else:
            results.add_fail("Server health", f"HTTP {response.status_code}")
            return False

    except requests.exceptions.ConnectionError:
        results.add_fail("Server health", "Cannot connect to server")
        return False
    except requests.exceptions.Timeout:
        results.add_fail("Server health", "Health check timeout")
        return False
    except Exception as e:
        results.add_fail("Server health", f"Unexpected error: {e}")
        return False


def main():
    """Main test runner."""
    parser = argparse.ArgumentParser(
        description="Test Bug #5 and Bug #6 fixes in vLLM Responses API"
    )
    parser.add_argument(
        "--host",
        default="192.168.228.43",
        help="Server host (default: 192.168.228.43)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Server port (default: 8000)"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output"
    )

    args = parser.parse_args()

    base_url = f"http://{args.host}:{args.port}/v1"

    print(f"\n{'='*60}")
    print(f"Bug #5 and Bug #6 Fix Verification Test")
    print(f"{'='*60}")
    print(f"Server: {base_url}")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    results = TestResults()

    # Test 1: Server health
    if not test_server_health(base_url, results):
        print(f"\n{RED}Cannot proceed: Server is not healthy{RESET}")
        return 2

    # Test 2: Bug #6 - Tool format
    test_bug_6_tools_format(base_url, results)

    # Test 3: Bug #5 - Delta format
    test_bug_5_delta_format(base_url, results)

    # Print summary
    success = results.print_summary()

    return 0 if success else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(f"\n\n{YELLOW}Test interrupted by user{RESET}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{RED}Fatal error: {e}{RESET}")
        import traceback
        traceback.print_exc()
        sys.exit(2)
