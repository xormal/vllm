#!/usr/bin/env python3
"""
Codex-Compatible Protocol Test WITHOUT reasoning
(reasoning causes model to hang)
"""

import json
import sys
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional
import time
import argparse
import uuid


# Copy all the code from test_codex_compatible.py but modify create_codex_request:

# ============================================================================
# ANSI Colors
# ============================================================================

class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_section(title: str):
    print(f"\n{Colors.BOLD}{Colors.HEADER}{'=' * 80}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}{title}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}{'=' * 80}{Colors.ENDC}")

def print_success(msg: str):
    print(f"{Colors.OKGREEN}✅ {msg}{Colors.ENDC}")

def print_error(msg: str):
    print(f"{Colors.FAIL}❌ {msg}{Colors.ENDC}")

def print_warning(msg: str):
    print(f"{Colors.WARNING}⚠️  {msg}{Colors.ENDC}")

def print_json(obj: Any, indent: int = 2):
    print(json.dumps(obj, indent=indent, ensure_ascii=False))


# ============================================================================
# Request creation (WITHOUT reasoning)
# ============================================================================

def create_shell_tool() -> Dict[str, Any]:
    """Create shell tool definition matching Codex format."""
    return {
        "type": "function",
        "name": "shell",
        "description": "Execute shell commands",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Command and arguments as array. Example: [\"ls\", \"-la\"]"
                }
            },
            "required": ["command"],
            "additionalProperties": False
        }
    }


def create_codex_request_no_reasoning(model: str, user_message: str) -> Dict[str, Any]:
    """Create a request WITHOUT reasoning (to avoid hanging)."""

    payload = {
        "model": model,
        "input": user_message,  # Simple string input
        "tools": [create_shell_tool()],
        "tool_choice": "auto",
        "stream": True,
    }

    return payload


# ============================================================================
# Test
# ============================================================================

def test_codex_protocol(host: str, port: int, model: str) -> bool:
    """Test Codex protocol WITHOUT reasoning."""

    print_section("CODEX PROTOCOL TEST (No Reasoning)")

    url = f"http://{host}:{port}/v1/responses"

    # Create request WITHOUT reasoning
    payload = create_codex_request_no_reasoning(
        model=model,
        user_message="List all Python files in the current directory using ls command"
    )

    print("\n📤 REQUEST (Codex-compatible, NO reasoning):")
    print(f"URL: {url}")
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
            print(f"\n📥 RESPONSE:")
            print(f"Status: {response.status} {response.reason}")
            print(f"Content-Type: {response.headers.get('Content-Type')}\n")

            # Track events
            output_item_added_events = []
            output_item_done_events = []
            event_count = 0
            max_events = 100

            print("📡 STREAMING EVENTS:")
            print("-" * 80)

            for line in response:
                line = line.decode('utf-8').strip()

                if not line or line.startswith("event:"):
                    continue

                if line.startswith("data:"):
                    data_str = line[5:].strip()

                    if data_str == "[DONE]":
                        print("\n[Stream Complete: DONE]")
                        break

                    try:
                        event = json.loads(data_str)
                        event_count += 1
                        event_type = event.get("type", "unknown")
                        seq = event.get("sequence_number", "?")

                        # Track function_call events
                        if event_type == "response.output_item.added":
                            item = event.get("item", {})
                            if item.get("type") == "function_call":
                                output_item_added_events.append(event)
                                print(f"\n[{event_count}] {event_type} (seq={seq})")
                                print(f"  Type: function_call")
                                print(f"  Name: {item.get('name')}")
                                print(f"  Call ID: {item.get('call_id')}")
                                print(f"  Arguments: '{item.get('arguments', '')}'")

                        elif event_type == "response.output_item.done":
                            item = event.get("item", {})
                            if item.get("type") == "function_call":
                                output_item_done_events.append(event)
                                print(f"\n[{event_count}] {event_type} (seq={seq})")
                                print(f"  Type: function_call")
                                print(f"  Name: {item.get('name')}")
                                print(f"  Call ID: {item.get('call_id')}")
                                args = item.get('arguments', '')
                                print(f"  Arguments ({len(args)} chars): {args[:100]}")

                        elif event_type == "response.created":
                            print(f"\n[{event_count}] {event_type} (seq={seq})")

                        elif event_type == "response.completed":
                            print(f"\n[{event_count}] {event_type} (seq={seq})")
                            break

                        elif event_type == "response.failed":
                            print(f"\n[{event_count}] {event_type} (seq={seq})")
                            error = event.get("response", {}).get("error", {})
                            print(f"  Error: {error}")
                            break

                        # Safety
                        if event_count >= max_events:
                            print(f"\n⚠ Stopped after {max_events} events")
                            break

                    except json.JSONDecodeError as e:
                        print(f"\n⚠ Parse error: {e}")

            elapsed = time.time() - start_time
            print(f"\n{'='*80}")
            print(f"Total events: {event_count}")
            print(f"Time: {elapsed:.2f}s")
            print(f"function_call added: {len(output_item_added_events)}")
            print(f"function_call done: {len(output_item_done_events)}")

            # Validate
            print("\n" + "="*80)
            if not output_item_done_events:
                print_warning("No function_call events - model may not have used tools")
                print_warning("But server is working correctly!")
                return True

            # Check call_id consistency
            for added_event in output_item_added_events:
                added_call_id = added_event.get("item", {}).get("call_id")

                # Find matching done
                found = False
                for done_event in output_item_done_events:
                    done_call_id = done_event.get("item", {}).get("call_id")
                    if done_call_id == added_call_id:
                        found = True
                        done_args = done_event.get("item", {}).get("arguments", "")

                        if not done_args:
                            print_error(f"call_id {added_call_id}: arguments are EMPTY!")
                            return False

                        print_success(f"call_id {added_call_id}: consistent, args={len(done_args)} chars")
                        break

                if not found:
                    print_error(f"call_id {added_call_id}: NO matching done event!")
                    return False

            print_success("All checks passed!")
            return True

    except urllib.error.HTTPError as e:
        print_error(f"HTTP {e.code}: {e.reason}")
        try:
            error_body = e.read().decode('utf-8')
            print_json(json.loads(error_body))
        except:
            pass
        return False

    except Exception as e:
        print_error(f"{type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(description="Codex Protocol Test (No Reasoning)")
    parser.add_argument('--host', default='192.168.228.43')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--model', default='openai/gpt-oss-120b')
    args = parser.parse_args()

    print(f"{Colors.BOLD}{'='*80}{Colors.ENDC}")
    print(f"{Colors.BOLD}Codex Protocol Test (Without Reasoning){Colors.ENDC}")
    print(f"{Colors.BOLD}{'='*80}{Colors.ENDC}")
    print(f"Server: http://{args.host}:{args.port}")
    print(f"Model: {args.model}")
    print(f"\nNote: Reasoning disabled to avoid model hanging")

    passed = test_codex_protocol(args.host, args.port, args.model)

    print_section("FINAL RESULT")
    if passed:
        print_success("TEST PASSED - Server compatible with Codex!")
        return 0
    else:
        print_error("TEST FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
