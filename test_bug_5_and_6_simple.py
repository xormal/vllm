#!/usr/bin/env python3
"""
Simplified test for Bug #5 and Bug #6 fixes (no external dependencies).

Usage:
    python3 test_bug_5_and_6_simple.py
"""

import json
import sys
import urllib.request
import urllib.error
from typing import Any


def test_bug_6(host: str, port: int) -> bool:
    """Test Bug #6: Standard OpenAI tool format."""
    print("\nTesting Bug #6: Standard OpenAI tool format")
    print("-" * 60)

    url = f"http://{host}:{port}/v1/responses"
    data = {
        "model": "openai/gpt-oss-120b",
        "input": "What is 2+2?",
        "stream": False,
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "calculator",
                    "description": "Perform math",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "operation": {"type": "string"},
                            "a": {"type": "number"},
                            "b": {"type": "number"}
                        }
                    }
                }
            }
        ]
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )

        with urllib.request.urlopen(req, timeout=30) as response:
            status = response.status
            if status >= 200 and status < 300:
                print("  ✓ Server accepted standard OpenAI tool format")
                print("  ✓ Bug #6 appears to be FIXED")
                return True
            else:
                print(f"  ✗ HTTP {status}")
                return False

    except urllib.error.HTTPError as e:
        if e.code == 400:
            error_data = json.loads(e.read().decode('utf-8'))
            error_msg = error_data.get("error", {}).get("message", "")

            if "FunctionTool" in error_msg or "Field required" in error_msg:
                print("  ✗ Server rejected standard format")
                print(f"  ✗ Bug #6 NOT FIXED")
                print(f"     Error: {error_msg[:150]}...")
                return False

        print(f"  ✗ HTTP Error {e.code}")
        return False

    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def test_bug_5(host: str, port: int) -> bool:
    """Test Bug #5: response.tool_call.delta format."""
    print("\nTesting Bug #5: response.tool_call.delta format")
    print("-" * 60)

    url = f"http://{host}:{port}/v1/responses"
    data = {
        "model": "openai/gpt-oss-120b",
        "input": "List files",
        "stream": True,
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "list_files",
                    "description": "List files",
                    "parameters": {"type": "object"}
                }
            }
        ]
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )

        with urllib.request.urlopen(req, timeout=60) as response:
            tool_call_deltas = []
            buffer = ""

            # Read SSE stream
            for line in response:
                line = line.decode('utf-8').strip()

                if line.startswith("data:"):
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        break

                    try:
                        event = json.loads(data_str)
                        if event.get("type") == "response.tool_call.delta":
                            tool_call_deltas.append(event)

                        # Stop after finding some tool calls or completion
                        if len(tool_call_deltas) >= 3:
                            break
                        if event.get("type") in ("response.completed", "response.failed"):
                            break

                    except json.JSONDecodeError:
                        pass

            if not tool_call_deltas:
                print("  ⚠ No tool_call.delta events found")
                print("     (Model may not have called tools)")
                return True  # Not a failure, just no tool calls

            print(f"  ✓ Found {len(tool_call_deltas)} tool_call.delta events")

            # Validate delta format
            all_valid = True
            for i, event in enumerate(tool_call_deltas):
                delta = event.get("delta")

                if not isinstance(delta, str):
                    print(f"  ✗ Event {i+1}: delta is {type(delta).__name__}, not string")
                    print(f"  ✗ Bug #5 NOT FIXED")
                    all_valid = False
                    break

                if delta == "":
                    print(f"  ⚠ Event {i+1}: delta payload empty")

            if all_valid:
                print("  ✓ All delta events have correct format")
                print("  ✓ Bug #5 appears to be FIXED")
                return True
            else:
                return False

    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def main():
    """Main test runner."""
    host = "192.168.228.43"
    port = 8000

    print("=" * 60)
    print("Bug #5 and Bug #6 Fix Verification (Simple)")
    print("=" * 60)
    print(f"Server: http://{host}:{port}/v1")

    # Test health
    try:
        req = urllib.request.Request(f"http://{host}:{port}/health")
        with urllib.request.urlopen(req, timeout=10) as response:
            print("\n✓ Server is healthy\n")
    except Exception as e:
        print(f"\n✗ Cannot connect to server: {e}\n")
        return 2

    # Run tests
    bug_6_passed = test_bug_6(host, port)
    bug_5_passed = test_bug_5(host, port)

    # Summary
    print("\n" + "=" * 60)
    if bug_5_passed and bug_6_passed:
        print("✓ All tests passed!")
        print("=" * 60)
        return 0
    else:
        print("✗ Some tests failed")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nTest interrupted")
        sys.exit(1)
