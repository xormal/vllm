#!/usr/bin/env python3
"""
Full debug test with tools - shows EVERY event
"""

import socket
import json
import time

def test_tools_full():
    host = "192.168.228.43"
    port = 8000

    payload = {
        "model": "openai/gpt-oss-120b",
        "input": "List Python files using ls",
        "stream": True,
        "tools": [{
            "type": "function",
            "name": "shell",
            "description": "Execute shell commands",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "array",
                        "items": {"type": "string"}
                    }
                },
                "required": ["command"]
            }
        }],
        "tool_choice": "auto",
    }

    body = json.dumps(payload)
    request = (
        f"POST /v1/responses HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        f"Content-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"Accept: text/event-stream\r\n"
        f"Connection: close\r\n"
        f"\r\n"
        f"{body}"
    )

    print("=" * 80)
    print("TOOLS FULL DEBUG TEST")
    print("=" * 80)
    print(f"\nPayload: {body}\n")

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10.0)

    try:
        sock.connect((host, port))
        sock.sendall(request.encode('utf-8'))
        print("✅ Request sent\n")

        # Read headers
        buffer = b""
        while b"\r\n\r\n" not in buffer:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buffer += chunk

        headers, body_start = buffer.split(b"\r\n\r\n", 1)
        print("HEADERS:")
        print(headers.decode('utf-8'))
        print("\nEVENTS:")
        print("-" * 80)

        sock.settimeout(None)
        buffer = body_start
        event_count = 0
        last_data = time.time()
        function_call_items = []

        while True:
            try:
                chunk = sock.recv(4096)
                if not chunk:
                    print("\n[Connection closed]")
                    break

                buffer += chunk
                last_data = time.time()

                # Decode and process events
                try:
                    text = buffer.decode('utf-8', errors='ignore')

                    if 'data:' in text:
                        lines = text.split('\n')
                        for line in lines:
                            if line.startswith('data:'):
                                event_count += 1
                                data_str = line[5:].strip()

                                if data_str == "[DONE]":
                                    print(f"\n[{event_count}] [DONE]")
                                    sock.close()

                                    # Print summary
                                    print("\n" + "=" * 80)
                                    print(f"Total events: {event_count}")
                                    print(f"Function calls found: {len(function_call_items)}")

                                    if function_call_items:
                                        print("\n✅ FUNCTION CALLS:")
                                        for fc in function_call_items:
                                            print(f"\n  Name: {fc.get('name')}")
                                            print(f"  Call ID: {fc.get('call_id')}")
                                            args = fc.get('arguments', '')
                                            print(f"  Arguments ({len(args)} chars): {args}")
                                        return True
                                    else:
                                        print("\n⚠️  NO FUNCTION CALLS")
                                        return False

                                try:
                                    event = json.loads(data_str)
                                    event_type = event.get('type', 'unknown')

                                    # Track ALL events but print selectively
                                    if 'function_call' in event_type or 'tool_call' in event_type:
                                        print(f"\n[{event_count}] ⭐ {event_type}")
                                        print(f"  Event: {json.dumps(event, indent=2)}")

                                    elif event_type == "response.output_item.added":
                                        item = event.get("item", {})
                                        print(f"\n[{event_count}] {event_type}")
                                        print(f"  Item type: {item.get('type')}")
                                        if item.get('type') == 'function_call':
                                            print(f"  ⭐ FUNCTION CALL ADDED!")
                                            print(f"     Name: {item.get('name')}")
                                            print(f"     Call ID: {item.get('call_id')}")

                                    elif event_type == "response.output_item.done":
                                        item = event.get("item", {})
                                        print(f"\n[{event_count}] {event_type}")
                                        print(f"  Item type: {item.get('type')}")
                                        if item.get('type') == 'function_call':
                                            print(f"  ⭐ FUNCTION CALL DONE!")
                                            print(f"     Name: {item.get('name')}")
                                            print(f"     Call ID: {item.get('call_id')}")
                                            print(f"     Arguments: {item.get('arguments', '')[:200]}")
                                            function_call_items.append(item)

                                    elif event_count % 10 == 0 or event_type in ['response.created', 'response.completed', 'response.failed']:
                                        print(f"[{event_count}] {event_type}")

                                except json.JSONDecodeError:
                                    if event_count <= 10:
                                        print(f"[{event_count}] (non-JSON): {data_str[:80]}")

                        buffer = b""

                except UnicodeDecodeError:
                    pass

                # Safety: stop if no data for 30 seconds
                if time.time() - last_data > 30:
                    print(f"\n⏱️  No data for 30 seconds")
                    break

                # Safety: stop after 200 events
                if event_count >= 200:
                    print(f"\n⚠️  Stopped at 200 events")
                    break

            except Exception as e:
                print(f"\n❌ Error: {e}")
                break

        print(f"\n⚠️  Stream ended without [DONE]")
        print(f"Total events: {event_count}")
        print(f"Function calls: {len(function_call_items)}")
        return len(function_call_items) > 0

    except Exception as e:
        print(f"\n❌ Connection error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        sock.close()


if __name__ == "__main__":
    success = test_tools_full()
    exit(0 if success else 1)
