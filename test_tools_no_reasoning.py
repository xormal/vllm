#!/usr/bin/env python3
"""
Test tools with reasoning explicitly disabled in request
"""

import json
import urllib.request
import time

def test_tools_no_reasoning():
    url = "http://192.168.228.43:8000/v1/responses"

    payload = {
        "model": "openai/gpt-oss-120b",
        "input": "List Python files using ls command",
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
        # Try to disable reasoning
        "reasoning": None,  # or False, or {"enabled": False}
    }

    print("=" * 80)
    print("TOOLS TEST (reasoning disabled in request)")
    print("=" * 80)
    print(f"\nPayload:\n{json.dumps(payload, indent=2)}\n")

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )

        start = time.time()
        with urllib.request.urlopen(req, timeout=60) as response:
            print(f"Status: {response.status}\n")

            event_count = 0
            function_calls = []

            for line in response:
                line = line.decode('utf-8').strip()
                if not line or line.startswith("event:"):
                    continue

                if line.startswith("data:"):
                    data_str = line[5:].strip()

                    if data_str == "[DONE]":
                        print("\n[DONE]")
                        break

                    try:
                        event = json.loads(data_str)
                        event_count += 1
                        event_type = event.get("type", "unknown")

                        print(f"[{event_count}] {event_type}")

                        # Track function calls
                        if event_type == "response.output_item.done":
                            item = event.get("item", {})
                            if item.get("type") == "function_call":
                                function_calls.append(item)
                                print(f"  ✅ Function call: {item.get('name')}")
                                print(f"     call_id: {item.get('call_id')}")
                                print(f"     arguments: {item.get('arguments', '')[:100]}")

                        if event_type == "response.completed":
                            break

                        if event_count >= 100:
                            print("\n[Stopped at 100 events]")
                            break

                    except json.JSONDecodeError:
                        pass

            elapsed = time.time() - start
            print(f"\nTotal events: {event_count}")
            print(f"Time: {elapsed:.2f}s")
            print(f"Function calls: {len(function_calls)}")

            if function_calls:
                print("\n✅ SUCCESS - Tool call generated!")
                for fc in function_calls:
                    print(f"\n  Name: {fc.get('name')}")
                    print(f"  Arguments: {fc.get('arguments', '')}")
                return True
            else:
                print("\n⚠️  No tool calls generated")
                return False

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_tools_no_reasoning()
    exit(0 if success else 1)
