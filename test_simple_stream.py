#!/usr/bin/env python3
"""
Simple streaming test to verify basic server functionality.
"""

import json
import urllib.request
import time

def test_simple_stream():
    url = "http://192.168.228.43:8000/v1/responses"

    # Minimal request - just text generation, no tools
    payload = {
        "model": "openai/gpt-oss-120b",
        "input": "Say hello in one word",
        "stream": True,
    }

    print("=" * 80)
    print("SIMPLE STREAMING TEST")
    print("=" * 80)
    print(f"\nRequest: {json.dumps(payload, indent=2)}")
    print(f"\nSending to: {url}")
    print("\nWaiting for events...\n")

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )

        start = time.time()
        with urllib.request.urlopen(req, timeout=30) as response:
            print(f"Status: {response.status} {response.reason}")
            print(f"Content-Type: {response.headers.get('Content-Type')}\n")

            event_count = 0
            for line in response:
                line = line.decode('utf-8').strip()
                if not line:
                    continue

                if line.startswith("event:"):
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

                        # Show some details
                        if event_type == "response.output_text.delta":
                            delta = event.get("delta", "")
                            print(f"    Text: {delta}")
                        elif event_type == "response.completed":
                            print(f"    ✅ Completed!")
                            break
                        elif event_type == "response.failed":
                            error = event.get("response", {}).get("error", {})
                            print(f"    ❌ Failed: {error}")
                            break

                        # Safety: stop after 20 events
                        if event_count >= 20:
                            print("\n[Stopped after 20 events]")
                            break

                    except json.JSONDecodeError as e:
                        print(f"Failed to parse: {e}")
                        print(f"Data: {data_str[:100]}")

            elapsed = time.time() - start
            print(f"\nTotal events: {event_count}")
            print(f"Time: {elapsed:.2f}s")

            if event_count > 0:
                print("\n✅ Server is streaming events!")
                return True
            else:
                print("\n❌ No events received!")
                return False

    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_simple_stream()
    exit(0 if success else 1)
