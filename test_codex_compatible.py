#!/usr/bin/env python3
"""
Codex-Compatible Protocol Test

This test replicates EXACTLY what Codex sends to /v1/responses endpoint
and validates server responses according to Codex expectations.

Usage:
    python3 test_codex_compatible.py [--host HOST] [--port PORT]
"""

import json
import sys
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional
import time
import argparse
import uuid


# ============================================================================
# ANSI Colors for terminal output
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
    UNDERLINE = '\033[4m'


def print_section(title: str):
    """Print section header."""
    print(f"\n{Colors.BOLD}{Colors.HEADER}{'=' * 80}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}{title}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}{'=' * 80}{Colors.ENDC}")


def print_subsection(title: str):
    """Print subsection header."""
    print(f"\n{Colors.BOLD}{Colors.OKCYAN}{'-' * 80}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.OKCYAN}{title}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.OKCYAN}{'-' * 80}{Colors.ENDC}")


def print_json(obj: Any, indent: int = 2):
    """Pretty print JSON object."""
    print(json.dumps(obj, indent=indent, ensure_ascii=False))


def print_success(msg: str):
    """Print success message."""
    print(f"{Colors.OKGREEN}✅ {msg}{Colors.ENDC}")


def print_error(msg: str):
    """Print error message."""
    print(f"{Colors.FAIL}❌ {msg}{Colors.ENDC}")


def print_warning(msg: str):
    """Print warning message."""
    print(f"{Colors.WARNING}⚠️  {msg}{Colors.ENDC}")


def print_info(msg: str):
    """Print info message."""
    print(f"{Colors.OKBLUE}ℹ️  {msg}{Colors.ENDC}")


# ============================================================================
# Codex Protocol Structures (matching codex-rs types)
# ============================================================================

BASE_INSTRUCTIONS = """You are Codex, an AI assistant developed by OpenAI to help developers write, edit, and understand code.

Your role is to:
- Understand user requests and provide helpful, accurate responses
- Execute shell commands when needed using the tools available
- Read, write, and modify files as requested
- Explain code and provide technical guidance
- Follow best practices for code quality and security

When using tools:
- Use the 'shell' tool to execute commands
- Always provide clear explanations of what you're doing
- Be cautious with destructive operations

Communication style:
- Be concise and direct
- Use technical language when appropriate
- Provide code examples when helpful
- Ask for clarification if requests are ambiguous
"""


def create_user_message(text: str) -> Dict[str, Any]:
    """Create a user message in Codex ResponseItem format."""
    return {
        "type": "message",
        "role": "user",
        "content": [
            {
                "type": "input_text",
                "text": text
            }
        ]
    }


def create_shell_tool() -> Dict[str, Any]:
    """Create shell tool definition matching Codex format."""
    return {
        "type": "function",
        "name": "shell",
        "description": "Execute shell commands. Use this to run command-line operations, list files, read file contents, etc.",
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


def create_codex_request(
    model: str,
    user_message: str,
    instructions: Optional[str] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    reasoning_effort: Optional[str] = None,
    conversation_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a request payload EXACTLY as Codex sends it.

    Matches: codex-rs/core/src/client.rs:241-254
    """
    if instructions is None:
        instructions = BASE_INSTRUCTIONS

    if tools is None:
        tools = [create_shell_tool()]

    if conversation_id is None:
        conversation_id = str(uuid.uuid4())

    payload = {
        "model": model,
        "instructions": instructions,
        "input": [create_user_message(user_message)],
        "tools": tools,
        "tool_choice": "auto",
        "parallel_tool_calls": True,
        "store": False,
        "stream": True,
        "include": [],
        "prompt_cache_key": conversation_id
    }

    # Add reasoning if specified
    if reasoning_effort:
        payload["reasoning"] = {
            "effort": reasoning_effort,
            "summary": "auto"
        }
        payload["include"] = ["reasoning.encrypted_content"]

    return payload


# ============================================================================
# Protocol Validation
# ============================================================================

class ProtocolValidator:
    """Validates server responses against Codex protocol expectations."""

    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: List[str] = []

    def validate_request_accepted(self, status_code: int, headers: Dict[str, str]) -> bool:
        """Validate that request was accepted."""
        if status_code != 200:
            self.errors.append(f"Expected status 200, got {status_code}")
            return False

        content_type = headers.get('Content-Type', headers.get('content-type', ''))
        if 'text/event-stream' not in content_type:
            self.errors.append(f"Expected Content-Type: text/event-stream, got: {content_type}")
            return False

        self.info.append("Request accepted with status 200")
        self.info.append(f"Content-Type: {content_type}")
        return True

    def validate_sse_event(self, event: Dict[str, Any], event_number: int) -> Optional[str]:
        """
        Validate SSE event structure.
        Returns event type if valid, None otherwise.
        """
        if "type" not in event:
            self.errors.append(f"Event #{event_number}: Missing 'type' field")
            return None

        event_type = event["type"]

        # Validate response field
        if "response" not in event:
            self.errors.append(f"Event #{event_number} ({event_type}): Missing 'response' field")
            return None

        response = event["response"]
        if not isinstance(response, dict):
            self.errors.append(f"Event #{event_number} ({event_type}): 'response' must be object, got {type(response).__name__}")
            return None

        if "id" not in response:
            self.errors.append(f"Event #{event_number} ({event_type}): Missing 'response.id'")
            return None

        return event_type

    def validate_output_item_done(self, event: Dict[str, Any], event_number: int) -> bool:
        """Validate response.output_item.done event structure."""
        if "item" not in event:
            self.errors.append(f"Event #{event_number}: output_item.done missing 'item' field")
            return False

        item = event["item"]
        if not isinstance(item, dict):
            self.errors.append(f"Event #{event_number}: 'item' must be object, got {type(item).__name__}")
            return False

        if "type" not in item:
            self.errors.append(f"Event #{event_number}: item missing 'type' field")
            return False

        item_type = item["type"]

        # Validate function_call structure
        if item_type == "function_call":
            return self._validate_function_call_item(item, event_number)

        return True

    def _validate_function_call_item(self, item: Dict[str, Any], event_number: int) -> bool:
        """Validate function_call item structure."""
        required_fields = ["name", "arguments", "call_id"]

        for field in required_fields:
            if field not in item:
                self.errors.append(f"Event #{event_number}: function_call missing '{field}'")
                return False

        # Validate arguments is a string
        if not isinstance(item["arguments"], str):
            self.errors.append(
                f"Event #{event_number}: function_call.arguments must be string, "
                f"got {type(item['arguments']).__name__}"
            )
            return False

        # Check if arguments is empty
        if not item["arguments"] or item["arguments"] == "":
            self.errors.append(
                f"Event #{event_number}: function_call.arguments is EMPTY! "
                f"This is Bug #5 - Codex will receive empty arguments and cannot execute the tool."
            )
            return False

        # Validate arguments is valid JSON
        try:
            parsed = json.loads(item["arguments"])
            self.info.append(f"Event #{event_number}: arguments valid JSON with {len(item['arguments'])} chars")
        except json.JSONDecodeError as e:
            self.errors.append(
                f"Event #{event_number}: function_call.arguments is not valid JSON: {e}"
            )
            return False

        return True

    def validate_tool_call_consistency(
        self,
        added_events: List[Dict[str, Any]],
        done_events: List[Dict[str, Any]]
    ) -> bool:
        """Validate consistency between output_item.added and output_item.done events."""
        if not added_events and not done_events:
            self.warnings.append("No tool call events found (model may have chosen not to use tools)")
            return True

        if not done_events:
            self.errors.append("Found output_item.added but no output_item.done - incomplete tool call!")
            return False

        # Check each added event has corresponding done event with same call_id
        all_valid = True
        for added_event in added_events:
            added_item = added_event.get("item", {})
            added_call_id = added_item.get("call_id")

            # Find matching done event
            done_event = None
            for de in done_events:
                done_item = de.get("item", {})
                if done_item.get("call_id") == added_call_id:
                    done_event = de
                    break

            if not done_event:
                self.errors.append(
                    f"call_id mismatch: output_item.added has call_id={added_call_id} "
                    f"but no matching output_item.done found. This is Bug #5!"
                )
                all_valid = False
            else:
                self.info.append(f"call_id {added_call_id}: consistent between added and done events")

        return all_valid

    def check_for_invalid_events(self, event_type: str, event_number: int) -> bool:
        """Check for events that Codex does NOT support."""
        # Events that Codex IGNORES (codex-rs/core/src/client.rs:882-887)
        ignored_events = [
            "response.tool_call.delta",  # This is the main problem!
            "response.content_part.done",
            "response.function_call_arguments.delta",
            "response.custom_tool_call_input.delta",
            "response.custom_tool_call_input.done",
            "response.in_progress",
            "response.output_text.done"
        ]

        if event_type in ignored_events:
            if event_type == "response.tool_call.delta":
                self.errors.append(
                    f"Event #{event_number}: CRITICAL - Server sent '{event_type}' event!\n"
                    f"    Codex IGNORES this event type (codex-rs/core/src/client.rs:883)\n"
                    f"    This causes Bug #5: empty arguments in function_call\n"
                    f"    FIX: Server must send 'response.output_item.done' instead"
                )
            else:
                self.warnings.append(
                    f"Event #{event_number}: Server sent '{event_type}' - "
                    f"Codex ignores this event type"
                )
            return False

        return True

    def print_report(self):
        """Print validation report."""
        print_subsection("PROTOCOL VALIDATION REPORT")

        if self.errors:
            print(f"\n{Colors.FAIL}{Colors.BOLD}ERRORS ({len(self.errors)}):{Colors.ENDC}")
            for i, error in enumerate(self.errors, 1):
                print(f"{Colors.FAIL}  {i}. {error}{Colors.ENDC}")

        if self.warnings:
            print(f"\n{Colors.WARNING}{Colors.BOLD}WARNINGS ({len(self.warnings)}):{Colors.ENDC}")
            for i, warning in enumerate(self.warnings, 1):
                print(f"{Colors.WARNING}  {i}. {warning}{Colors.ENDC}")

        if self.info:
            print(f"\n{Colors.OKBLUE}{Colors.BOLD}INFO ({len(self.info)}):{Colors.ENDC}")
            for i, info in enumerate(self.info, 1):
                print(f"{Colors.OKBLUE}  {i}. {info}{Colors.ENDC}")

        print()
        if not self.errors:
            print_success("No protocol errors detected!")
            return True
        else:
            print_error(f"Found {len(self.errors)} protocol error(s)")
            return False


# ============================================================================
# Tests
# ============================================================================

def test_codex_protocol(host: str, port: int, model: str) -> bool:
    """
    Test full Codex protocol compatibility.

    This test replicates EXACTLY what Codex does:
    1. Send request with all required fields
    2. Parse SSE stream
    3. Validate event structure
    4. Check for tool call consistency
    """
    print_section("CODEX PROTOCOL COMPATIBILITY TEST")

    url = f"http://{host}:{port}/v1/responses"
    conversation_id = str(uuid.uuid4())

    # Create request exactly as Codex does
    payload = create_codex_request(
        model=model,
        user_message="List all Python files in the current directory using ls command",
        reasoning_effort="high",
        conversation_id=conversation_id
    )

    print("\n📤 REQUEST (Codex-compatible):")
    print(f"URL: {url}")
    print(f"Method: POST")
    print(f"Content-Type: application/json")
    print(f"\nPayload structure:")
    print(f"  - model: {payload['model']}")
    print(f"  - instructions: {len(payload['instructions'])} chars")
    print(f"  - input: {len(payload['input'])} message(s)")
    print(f"  - tools: {len(payload['tools'])} tool(s)")
    print(f"  - tool_choice: {payload['tool_choice']}")
    print(f"  - parallel_tool_calls: {payload['parallel_tool_calls']}")
    print(f"  - reasoning: {payload.get('reasoning', 'None')}")
    print(f"  - stream: {payload['stream']}")
    print(f"  - store: {payload['store']}")
    print(f"  - prompt_cache_key: {payload['prompt_cache_key'][:16]}...")

    print("\nFull payload:")
    print_json(payload)

    print("\n🔄 Sending request...")
    start_time = time.time()

    validator = ProtocolValidator()

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={
                'Content-Type': 'application/json',
                'Accept': 'text/event-stream'  # Codex always sends this
            }
        )

        with urllib.request.urlopen(req, timeout=60) as response:
            elapsed = time.time() - start_time

            print(f"\n📥 RESPONSE:")
            print(f"Status: {response.status} {response.reason}")
            print(f"Time: {elapsed:.2f}s")

            headers_dict = dict(response.headers)
            print(f"\nHeaders:")
            for key, value in headers_dict.items():
                print(f"  {key}: {value}")

            # Validate response headers
            if not validator.validate_request_accepted(response.status, headers_dict):
                validator.print_report()
                return False

            # Track events
            all_events = []
            output_item_added_events = []
            output_item_done_events = []
            event_count = 0
            max_events = 200

            print(f"\n📡 STREAMING EVENTS:")
            print("-" * 80)

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
                        event_count += 1
                        all_events.append(event)

                        # Validate event structure
                        event_type = validator.validate_sse_event(event, event_count)
                        if not event_type:
                            continue

                        # Check for invalid events
                        validator.check_for_invalid_events(event_type, event_count)

                        seq_num = event.get("sequence_number", "?")

                        # Track and display relevant events
                        if event_type == "response.created":
                            print(f"\n[Event #{event_count}] {event_type} (seq={seq_num})")
                            print(f"  Response ID: {event['response']['id']}")

                        elif event_type == "response.output_item.added":
                            item = event.get("item", {})
                            item_type = item.get("type")

                            if item_type == "function_call":
                                output_item_added_events.append(event)
                                print(f"\n[Event #{event_count}] {event_type} (seq={seq_num})")
                                print(f"  Item type: function_call")
                                print(f"  Name: {item.get('name', '?')}")
                                print(f"  Call ID: {item.get('call_id', '?')}")
                                print(f"  Arguments: '{item.get('arguments', '')}'")

                        elif event_type == "response.output_item.done":
                            item = event.get("item", {})
                            item_type = item.get("type")

                            # Validate structure
                            validator.validate_output_item_done(event, event_count)

                            if item_type == "function_call":
                                output_item_done_events.append(event)
                                print(f"\n[Event #{event_count}] {event_type} (seq={seq_num})")
                                print(f"  Item type: function_call")
                                print(f"  Name: {item.get('name', '?')}")
                                print(f"  Call ID: {item.get('call_id', '?')}")
                                args = item.get('arguments', '')
                                print(f"  Arguments length: {len(args)} chars")
                                if len(args) > 0:
                                    print(f"  Arguments: {args[:100]}{'...' if len(args) > 100 else ''}")
                                else:
                                    print(f"  Arguments: {Colors.FAIL}EMPTY!{Colors.ENDC}")
                            elif item_type == "reasoning":
                                print(f"\n[Event #{event_count}] {event_type} - reasoning (seq={seq_num})")
                                content = item.get("content", [])
                                if content and len(content) > 0:
                                    text = content[0].get("text", "")
                                    print(f"  Reasoning: {text[:100]}...")
                            elif item_type == "message":
                                print(f"\n[Event #{event_count}] {event_type} - message (seq={seq_num})")

                        elif event_type == "response.output_text.delta":
                            # Only show first few
                            if event_count <= 5:
                                delta = event.get("delta", "")
                                print(f"\n[Event #{event_count}] {event_type}: '{delta[:50]}...'")

                        elif event_type == "response.reasoning_text.delta":
                            # Only show first few
                            if event_count <= 3:
                                delta = event.get("delta", "")
                                print(f"\n[Event #{event_count}] {event_type}: '{delta[:50]}...'")

                        elif event_type == "response.completed":
                            print(f"\n[Event #{event_count}] {event_type} (seq={seq_num})")
                            resp = event.get("response", {})
                            usage = resp.get("usage", {})
                            if usage:
                                print(f"  Usage: {usage}")
                            break

                        elif event_type == "response.failed":
                            print(f"\n[Event #{event_count}] {event_type} (seq={seq_num})")
                            error = event.get("response", {}).get("error", {})
                            print(f"  Error: {error}")
                            break

                        # Safety limit
                        if event_count >= max_events:
                            print(f"\n⚠ Stopped after {max_events} events (safety limit)")
                            break

                    except json.JSONDecodeError as e:
                        print(f"\n⚠ Failed to parse JSON: {e}")
                        print(f"  Data: {data_str[:200]}...")
                        validator.errors.append(f"Failed to parse SSE event: {e}")

            elapsed = time.time() - start_time
            print(f"\n{'='*80}")
            print(f"Stream ended. Time: {elapsed:.2f}s")
            print(f"Total events: {event_count}")
            print(f"output_item.added (function_call): {len(output_item_added_events)}")
            print(f"output_item.done (function_call): {len(output_item_done_events)}")

            # Validate tool call consistency
            validator.validate_tool_call_consistency(
                output_item_added_events,
                output_item_done_events
            )

            # Print validation report
            validator.print_report()

            return len(validator.errors) == 0

    except urllib.error.HTTPError as e:
        elapsed = time.time() - start_time
        print(f"\n{Colors.FAIL}❌ HTTP ERROR:{Colors.ENDC}")
        print(f"   Status: {e.code} {e.reason}")
        print(f"   Time: {elapsed:.2f}s")

        try:
            error_body = e.read().decode('utf-8')
            error_data = json.loads(error_body)
            print(f"\n   Error details:")
            print_json(error_data)

            # Analyze error
            error_msg = error_data.get("error", {}).get("message", "")

            print(f"\n{Colors.FAIL}{Colors.BOLD}🔍 ERROR ANALYSIS:{Colors.ENDC}")

            if "instructions" in error_msg.lower():
                print_error("Server does not accept 'instructions' field")
                print_info("Fix: Add 'instructions' field support in request schema")

            if "tool_choice" in error_msg.lower():
                print_error("Server does not accept 'tool_choice' field")
                print_info("Fix: Add 'tool_choice' field support in request schema")

            if "parallel_tool_calls" in error_msg.lower():
                print_error("Server does not accept 'parallel_tool_calls' field")
                print_info("Fix: Add 'parallel_tool_calls' field support in request schema")

            if "input" in error_msg.lower() and "array" in error_msg.lower():
                print_error("Server does not accept 'input' as array of ResponseItem objects")
                print_info("Fix: Update input field to accept Union[str, List[ResponseItem]]")

            validator.errors.append(f"HTTP {e.code}: {error_msg}")

        except Exception as parse_error:
            print(f"Could not parse error body: {parse_error}")

        validator.print_report()
        return False

    except urllib.error.URLError as e:
        print(f"\n{Colors.FAIL}❌ CONNECTION ERROR:{Colors.ENDC}")
        print(f"   {e.reason}")
        print(f"   Cannot connect to {url}")
        return False

    except Exception as e:
        print(f"\n{Colors.FAIL}❌ UNEXPECTED ERROR:{Colors.ENDC}")
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
            print_success("Server is healthy and responding")
            return True

    except urllib.error.HTTPError as e:
        print(f"   Status: {e.code} {e.reason}")
        print_warning("Health check returned error status")
        return False

    except urllib.error.URLError as e:
        print(f"   Error: {e.reason}")
        print_error("Cannot connect to server")
        return False

    except Exception as e:
        print(f"   Error: {e}")
        print_error("Health check failed")
        return False


# ============================================================================
# Main
# ============================================================================

def main():
    """Main test runner."""
    parser = argparse.ArgumentParser(
        description="Codex-Compatible Protocol Test",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
This test replicates EXACTLY what Codex sends to the /v1/responses endpoint
and validates server responses according to Codex expectations.

The test checks for:
  1. Request compatibility (all required fields present)
  2. SSE event structure validity
  3. Tool call consistency (Bug #5)
  4. Protocol compliance with Codex expectations

Exit codes:
  0 - All tests passed
  1 - Tests failed (protocol errors detected)
  2 - Server not healthy or connection failed
"""
    )

    parser.add_argument(
        '--host',
        default='192.168.228.43',
        help='Server host (default: 192.168.228.43)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=8000,
        help='Server port (default: 8000)'
    )
    parser.add_argument(
        '--model',
        default='openai/gpt-oss-120b',
        help='Model name (default: openai/gpt-oss-120b)'
    )
    parser.add_argument(
        '--skip-health',
        action='store_true',
        help='Skip health check'
    )

    args = parser.parse_args()

    print(f"{Colors.BOLD}{Colors.HEADER}{'=' * 80}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}          Codex Protocol Compatibility Test{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}{'=' * 80}{Colors.ENDC}")
    print(f"Server: http://{args.host}:{args.port}/v1")
    print(f"Model: {args.model}")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"\nThis test replicates EXACTLY what Codex sends and expects.")
    print(f"Reference: codex-rs/core/src/client.rs and client_common.rs")

    # Health check
    if not args.skip_health:
        if not test_health(args.host, args.port):
            print(f"\n{Colors.FAIL}{'=' * 80}{Colors.ENDC}")
            print(f"{Colors.FAIL}❌ ABORTED: Server is not healthy{Colors.ENDC}")
            print(f"{Colors.FAIL}{'=' * 80}{Colors.ENDC}")
            return 2

    # Run main test
    passed = test_codex_protocol(args.host, args.port, args.model)

    # Final summary
    print_section("FINAL SUMMARY")

    if passed:
        print_success("ALL TESTS PASSED")
        print(f"\n{Colors.OKGREEN}✓ Server fully compatible with Codex protocol{Colors.ENDC}")
        print(f"{Colors.OKGREEN}✓ Request format accepted{Colors.ENDC}")
        print(f"{Colors.OKGREEN}✓ SSE events properly structured{Colors.ENDC}")
        print(f"{Colors.OKGREEN}✓ Tool calls working correctly{Colors.ENDC}")
        print(f"\n{Colors.BOLD}{Colors.OKGREEN}{'=' * 80}{Colors.ENDC}")
        print(f"{Colors.BOLD}{Colors.OKGREEN}✅ READY FOR CODEX!{Colors.ENDC}")
        print(f"{Colors.BOLD}{Colors.OKGREEN}{'=' * 80}{Colors.ENDC}")
        return 0
    else:
        print_error("TESTS FAILED")
        print(f"\n{Colors.FAIL}✗ Server has protocol compatibility issues{Colors.ENDC}")
        print(f"\n{Colors.BOLD}📝 REQUIRED FIXES:{Colors.ENDC}")
        print(f"   1. Review error messages above")
        print(f"   2. Fix identified protocol issues")
        print(f"   3. Re-run this test until all tests pass")
        print(f"\n{Colors.BOLD}Reference implementation:{Colors.ENDC}")
        print(f"   - Request format: codex-rs/core/src/client_common.rs:266-284")
        print(f"   - SSE parsing: codex-rs/core/src/client.rs:685-900")
        print(f"   - Tool format: codex-rs/core/src/client_common.rs:293-342")
        print(f"\n{Colors.FAIL}{'=' * 80}{Colors.ENDC}")
        print(f"{Colors.FAIL}❌ NOT READY FOR CODEX{Colors.ENDC}")
        print(f"{Colors.FAIL}{'=' * 80}{Colors.ENDC}")
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(f"\n\n{Colors.WARNING}⚠ Test interrupted by user{Colors.ENDC}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Colors.FAIL}💥 FATAL ERROR: {e}{Colors.ENDC}")
        import traceback
        traceback.print_exc()
        sys.exit(2)
