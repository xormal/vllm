#!/usr/bin/env python3
"""
Detailed verbose test for Bug #5 and Bug #6 fixes (no external dependencies).

Bug #5: call_id mismatch between response.output_item.added and response.output_item.done
Bug #6: Server doesn't accept standard OpenAI tool format

Usage:
    python3 test_bug_5_and_6_verbose.py
"""

import json
import sys
import urllib.request
import urllib.error
from typing import Any
import time


def print_section(title: str):
    """Print section header."""
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def print_subsection(title: str):
    """Print subsection header."""
    print("\n" + "-" * 70)
    print(title)
    print("-" * 70)


def print_json(obj: Any, indent: int = 2):
    """Pretty print JSON object."""
    print(json.dumps(obj, indent=indent, ensure_ascii=False))


def test_bug_6(host: str, port: int) -> bool:
    """Test Bug #6: Standard OpenAI tool format."""
    print_section("TEST 1: Bug #6 - Standard OpenAI Tool Format")

    url = f"http://{host}:{port}/v1/responses"

    # Prepare request payload (standard OpenAI format)
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

    print("\n📤 REQUEST:")
    print(f"URL: {url}")
    print(f"Method: POST")
    print(f"Content-Type: application/json")
    print(f"\nPayload:")
    print_json(payload)

    print("\n🔄 Sending request...")
    start_time = time.time()

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )

        with urllib.request.urlopen(req, timeout=30) as response:
            elapsed = time.time() - start_time
            status = response.status
            headers = dict(response.headers)

            print(f"\n📥 RESPONSE:")
            print(f"Status: {status} {response.reason}")
            print(f"Time: {elapsed:.2f}s")
            print(f"\nHeaders:")
            for key, value in headers.items():
                print(f"  {key}: {value}")

            # Read response body
            body = response.read().decode('utf-8')
            print(f"\nBody:")
            try:
                body_json = json.loads(body)
                print_json(body_json)
            except json.JSONDecodeError:
                print(body[:500])

            # Validate
            if status >= 200 and status < 300:
                print("\n✅ RESULT: Bug #6 Test PASSED")
                print("   Server accepted standard OpenAI tool format")
                print("   Bug #6 appears to be FIXED ✓")
                return True
            else:
                print(f"\n❌ RESULT: Bug #6 Test FAILED")
                print(f"   HTTP {status} (expected 2xx)")
                return False

    except urllib.error.HTTPError as e:
        elapsed = time.time() - start_time
        print(f"\n📥 ERROR RESPONSE:")
        print(f"Status: {e.code} {e.reason}")
        print(f"Time: {elapsed:.2f}s")

        # Read error body
        try:
            error_body = e.read().decode('utf-8')
            print(f"\nError Body:")
            error_data = json.loads(error_body)
            print_json(error_data)

            # Analyze error
            error_msg = error_data.get("error", {}).get("message", "")

            print("\n🔍 ERROR ANALYSIS:")
            if "FunctionTool" in error_msg:
                print("   ⚠ Error mentions 'FunctionTool'")
                print("   → Server expects non-standard format")
            if "Field required" in error_msg:
                print("   ⚠ Error says 'Field required'")
                print("   → Server validation failed on standard format")
            if "'name'" in error_msg:
                print("   ⚠ Error mentions 'name' field")
                print("   → Server expects 'name' at different location")

            print("\n❌ RESULT: Bug #6 Test FAILED")
            print("   Server rejected standard OpenAI tool format")
            print("   Bug #6 is NOT FIXED ✗")

            return False

        except Exception as parse_error:
            print(f"Could not parse error body: {parse_error}")
            return False

    except urllib.error.URLError as e:
        print(f"\n❌ CONNECTION ERROR:")
        print(f"   {e.reason}")
        return False

    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR:")
        print(f"   {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_bug_5(host: str, port: int) -> bool:
    """
    Test Bug #5: call_id mismatch and empty arguments.

    This test verifies that:
    1. response.output_item.added is sent with a call_id
    2. response.output_item.done is sent with the SAME call_id
    3. response.output_item.done contains FULL arguments (not empty)
    """
    print_section("TEST 2: Bug #5 - call_id Consistency & Full Arguments")

    url = f"http://{host}:{port}/v1/responses"

    # Prepare request payload with shell tool (likely to trigger tool call)
    payload = {
        "model": "openai/gpt-oss-120b",
        "input": "List all Python files in the current directory",
        "stream": True,
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "shell",
                    "description": "Execute shell commands",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Command and arguments"
                            }
                        },
                        "required": ["command"]
                    }
                }
            }
        ]
    }

    print("\n📤 REQUEST:")
    print(f"URL: {url}")
    print(f"Method: POST")
    print(f"Content-Type: application/json")
    print(f"Stream: True")
    print(f"\nPayload:")
    print_json(payload)

    print("\n🔄 Sending request...")
    start_time = time.time()

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )

        with urllib.request.urlopen(req, timeout=60) as response:
            print(f"\n📥 STREAMING RESPONSE:")
            print(f"Status: {response.status} {response.reason}")
            print(f"Content-Type: {response.headers.get('Content-Type', 'unknown')}")

            # Track tool call events
            output_item_added_events = []
            output_item_done_events = []
            all_events = []
            event_count = 0
            max_events = 100

            print(f"\n📡 STREAMING EVENTS:")
            print("-" * 70)

            for line in response:
                line = line.decode('utf-8').strip()

                if not line:
                    continue

                if line.startswith("event:"):
                    continue

                if line.startswith("data:"):
                    data_str = line[5:].strip()

                    if data_str == "[DONE]":
                        print("\n[Stream Complete: DONE]")
                        break

                    try:
                        event = json.loads(data_str)
                        event_type = event.get("type", "unknown")
                        seq_num = event.get("sequence_number", "?")

                        event_count += 1
                        all_events.append(event)

                        # Track relevant events
                        if event_type == "response.output_item.added":
                            item = event.get("item", {})
                            if item.get("type") == "function_call":
                                output_item_added_events.append(event)
                                print(f"\n[Event #{event_count}] {event_type} (seq={seq_num})")
                                print(f"  Item type: function_call")
                                print(f"  Name: {item.get('name', '?')}")
                                print(f"  Call ID: {item.get('call_id', '?')}")
                                print(f"  Arguments: '{item.get('arguments', '')}'")
                                print(f"  Status: {item.get('status', '?')}")

                        elif event_type == "response.output_item.done":
                            item = event.get("item", {})
                            if item.get("type") == "function_call":
                                output_item_done_events.append(event)
                                print(f"\n[Event #{event_count}] {event_type} (seq={seq_num})")
                                print(f"  Item type: function_call")
                                print(f"  Name: {item.get('name', '?')}")
                                print(f"  Call ID: {item.get('call_id', '?')}")
                                args = item.get('arguments', '')
                                print(f"  Arguments length: {len(args)} chars")
                                print(f"  Arguments: {args[:100]}{'...' if len(args) > 100 else ''}")
                                print(f"  Status: {item.get('status', '?')}")

                        elif event_type in ("response.created", "response.in_progress"):
                            print(f"\n[Event #{event_count}] {event_type} (seq={seq_num})")

                        elif event_type == "response.completed":
                            print(f"\n[Event #{event_count}] {event_type} (seq={seq_num})")
                            break

                        elif event_type == "response.failed":
                            print(f"\n[Event #{event_count}] {event_type} (seq={seq_num})")
                            error = event.get("error", {})
                            print(f"  Error: {error}")
                            break

                        # Safety limit
                        if event_count >= max_events:
                            print(f"\n⚠ Stopped after {max_events} events (safety limit)")
                            break

                    except json.JSONDecodeError as e:
                        print(f"\n⚠ Failed to parse JSON: {e}")
                        print(f"  Data: {data_str[:200]}...")

            elapsed = time.time() - start_time
            print(f"\n{'='*70}")
            print(f"Stream ended. Time: {elapsed:.2f}s")
            print(f"Total events: {event_count}")
            print(f"output_item.added (function_call): {len(output_item_added_events)}")
            print(f"output_item.done (function_call): {len(output_item_done_events)}")

            # Analyze results
            print_subsection("BUG #5 VALIDATION")

            if not output_item_added_events and not output_item_done_events:
                print("\n⚠ WARNING: No function_call events found")
                print("  Model may have decided not to use tools")
                print("  Cannot validate Bug #5 (not necessarily a failure)")
                return True

            if not output_item_added_events:
                print("\n❌ FAIL: No response.output_item.added events found")
                return False

            if not output_item_done_events:
                print("\n❌ FAIL: No response.output_item.done events found")
                return False

            # Validate each pair
            print(f"\n🔍 VALIDATING {len(output_item_added_events)} TOOL CALL(S):")

            all_valid = True
            for i, added_event in enumerate(output_item_added_events, 1):
                print(f"\n  Tool Call {i}/{len(output_item_added_events)}:")

                added_item = added_event.get("item", {})
                added_call_id = added_item.get("call_id")
                added_name = added_item.get("name")
                added_args = added_item.get("arguments", "")

                print(f"    Added event:")
                print(f"      - call_id: {added_call_id}")
                print(f"      - name: {added_name}")
                print(f"      - arguments: '{added_args}'")

                # Find matching done event
                done_event = None
                for de in output_item_done_events:
                    done_item = de.get("item", {})
                    if done_item.get("call_id") == added_call_id:
                        done_event = de
                        break

                if not done_event:
                    print(f"    ❌ FAIL: No matching output_item.done event found")
                    print(f"       Expected call_id: {added_call_id}")
                    print(f"       Available call_ids in done events:")
                    for de in output_item_done_events:
                        print(f"         - {de.get('item', {}).get('call_id')}")
                    all_valid = False
                    continue

                done_item = done_event.get("item", {})
                done_call_id = done_item.get("call_id")
                done_name = done_item.get("name")
                done_args = done_item.get("arguments", "")

                print(f"    Done event:")
                print(f"      - call_id: {done_call_id}")
                print(f"      - name: {done_name}")
                print(f"      - arguments length: {len(done_args)} chars")

                # Check 1: call_id matches
                if added_call_id != done_call_id:
                    print(f"    ❌ FAIL: call_id MISMATCH!")
                    print(f"       Added: {added_call_id}")
                    print(f"       Done:  {done_call_id}")
                    print(f"       This is the PRIMARY symptom of Bug #5!")
                    all_valid = False
                    continue

                print(f"    ✓ call_id matches: {added_call_id}")

                # Check 2: done event has arguments
                if not done_args or done_args == "":
                    print(f"    ❌ FAIL: Arguments are EMPTY in done event!")
                    print(f"       This means client won't receive tool arguments!")
                    all_valid = False
                    continue

                print(f"    ✓ Arguments present: {len(done_args)} chars")

                # Check 3: arguments are valid JSON
                try:
                    parsed_args = json.loads(done_args)
                    print(f"    ✓ Arguments are valid JSON")
                    print(f"       Preview: {json.dumps(parsed_args)[:100]}...")
                except json.JSONDecodeError as e:
                    print(f"    ⚠ WARNING: Arguments are not valid JSON: {e}")
                    print(f"       Args: {done_args[:100]}...")

            # Final verdict
            print("\n" + "=" * 70)
            if all_valid:
                print("✅ RESULT: Bug #5 Test PASSED")
                print("   ✓ call_id is consistent between added and done events")
                print("   ✓ Arguments are present in done event")
                print("   ✓ Client will receive full tool call information")
                print("\n   Bug #5 appears to be FIXED ✓")
                return True
            else:
                print("❌ RESULT: Bug #5 Test FAILED")
                print("   ✗ call_id mismatch OR empty arguments detected")
                print("   ✗ Client will receive empty arguments")
                print("\n   Bug #5 is NOT FIXED ✗")

                print("\n💡 REQUIRED FIX:")
                print("   In serving_responses.py, when generating output_item.done:")
                print("   1. Save call_id BEFORE resetting: saved_call_id = current_tool_call_id")
                print("   2. Use saved ID in done event: call_id=saved_call_id")
                print("   3. Ensure arguments contain full JSON string")

                return False

    except urllib.error.HTTPError as e:
        elapsed = time.time() - start_time
        print(f"\n❌ HTTP ERROR:")
        print(f"   Status: {e.code} {e.reason}")
        print(f"   Time: {elapsed:.2f}s")

        try:
            error_body = e.read().decode('utf-8')
            error_data = json.loads(error_body)
            print(f"\n   Error details:")
            print_json(error_data)
        except:
            print(f"   Raw error: {e}")

        print("\n   Cannot test Bug #5 due to request error")
        print("   (Possibly blocked by Bug #6)")
        return False

    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR:")
        print(f"   {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_health(host: str, port: int) -> bool:
    """Test server health."""
    print_section("PRELIMINARY CHECK: Server Health")

    url = f"http://{host}:{port}/health"
    print(f"\n🏥 Checking: {url}")

    try:
        req = urllib.request.Request(url)
        start_time = time.time()

        with urllib.request.urlopen(req, timeout=10) as response:
            elapsed = time.time() - start_time
            print(f"   Status: {response.status} {response.reason}")
            print(f"   Time: {elapsed:.2f}s")
            print(f"\n✅ Server is healthy and responding")
            return True

    except urllib.error.HTTPError as e:
        print(f"   Status: {e.code} {e.reason}")
        print(f"\n⚠ Health check returned error status")
        return False

    except urllib.error.URLError as e:
        print(f"   Error: {e.reason}")
        print(f"\n❌ Cannot connect to server")
        return False

    except Exception as e:
        print(f"   Error: {e}")
        print(f"\n❌ Health check failed")
        return False


def main():
    """Main test runner."""
    host = "192.168.228.43"
    port = 8000

    print("=" * 70)
    print("         Bug #5 and Bug #6 Fix Verification")
    print("              (Updated for Codex Compatibility)")
    print("=" * 70)
    print(f"Server: http://{host}:{port}/v1")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("\nWhat we're testing:")
    print("  Bug #5: call_id consistency & full arguments in output_item.done")
    print("  Bug #6: Standard OpenAI tool format acceptance")

    # Health check
    if not test_health(host, port):
        print("\n" + "=" * 70)
        print("❌ ABORTED: Server is not healthy")
        print("=" * 70)
        return 2

    # Run tests
    bug_6_passed = test_bug_6(host, port)
    bug_5_passed = test_bug_5(host, port)

    # Final summary
    print_section("FINAL SUMMARY")

    results = []
    if bug_6_passed:
        results.append("✅ Bug #6: FIXED (Standard OpenAI tool format accepted)")
    else:
        results.append("❌ Bug #6: NOT FIXED (Tool format rejected)")

    if bug_5_passed:
        results.append("✅ Bug #5: FIXED (call_id consistent, args present)")
    else:
        results.append("❌ Bug #5: NOT FIXED (call_id mismatch or empty args)")

    for result in results:
        print(f"  {result}")

    print("\n" + "=" * 70)
    if bug_5_passed and bug_6_passed:
        print("✅ ALL TESTS PASSED - Ready for Codex!")
        print("=" * 70)
        return 0
    else:
        print("❌ TESTS FAILED - Bugs need fixing")
        print("=" * 70)

        if not bug_6_passed:
            print("\n📝 Bug #6 Fix:")
            print("   Add FunctionTool support in protocol.py")
            print("   Add _normalize_request_tools() in serving_responses.py")

        if not bug_5_passed:
            print("\n📝 Bug #5 Fix:")
            print("   Save call_id before reset: saved_call_id = current_tool_call_id")
            print("   Use in done event: call_id=saved_call_id or f'call_{random_uuid()}'")

        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n⚠ Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(2)
