#!/usr/bin/env python3
"""
Test raw SSE stream - shows EXACTLY what server sends.
No timeout, raw bytes.
"""

import socket
import json
import time

def test_raw_sse():
    host = "192.168.228.43"
    port = 8000

    payload = {
        "model": "openai/gpt-oss-120b",
        "input": "Say hello",
        "stream": True,
    }

    # Build HTTP request manually
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
    print("RAW SSE TEST")
    print("=" * 80)
    print(f"\nConnecting to {host}:{port}")
    print(f"Request: POST /v1/responses")
    print(f"Payload: {body}\n")

    # Open raw socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10.0)  # 10 second timeout for initial response

    try:
        sock.connect((host, port))
        print("✅ Connected\n")

        # Send request
        sock.sendall(request.encode('utf-8'))
        print("✅ Request sent\n")

        # Read response
        print("📥 RESPONSE (raw bytes):")
        print("-" * 80)

        buffer = b""
        event_count = 0
        start = time.time()
        last_data = start

        # Read headers first
        while b"\r\n\r\n" not in buffer:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buffer += chunk

        headers, body_start = buffer.split(b"\r\n\r\n", 1)
        print("HEADERS:")
        print(headers.decode('utf-8', errors='ignore'))
        print()
        print("BODY:")

        # Now read body with NO timeout (wait for server)
        sock.settimeout(None)
        buffer = body_start

        while True:
            try:
                chunk = sock.recv(4096)
                if not chunk:
                    print("\n[Server closed connection]")
                    break

                buffer += chunk
                last_data = time.time()

                # Try to decode and print
                try:
                    text = buffer.decode('utf-8', errors='ignore')

                    # Look for complete events (data: ... \n\n)
                    if 'data:' in text:
                        lines = text.split('\n')
                        for line in lines:
                            if line.startswith('data:'):
                                event_count += 1
                                data_str = line[5:].strip()

                                if data_str == "[DONE]":
                                    print(f"\n[{event_count}] [DONE]")
                                    sock.close()
                                    return True

                                try:
                                    event = json.loads(data_str)
                                    event_type = event.get('type', 'unknown')
                                    print(f"[{event_count}] {event_type}")
                                except:
                                    print(f"[{event_count}] {data_str[:80]}...")

                        buffer = b""  # Clear buffer after printing

                except UnicodeDecodeError:
                    pass

                # Safety: stop after 20 seconds of no data
                if time.time() - last_data > 20:
                    print(f"\n⚠️  No data for 20 seconds, stopping")
                    break

            except socket.timeout:
                print(f"\n⏱️  Timeout waiting for data")
                break
            except Exception as e:
                print(f"\n❌ Error: {e}")
                break

        elapsed = time.time() - start
        print(f"\nTotal events: {event_count}")
        print(f"Time: {elapsed:.2f}s")

        if event_count == 0:
            print("\n❌ NO EVENTS RECEIVED!")
            return False
        elif event_count == 1:
            print("\n⚠️  Only 1 event - server may not be streaming")
            return False
        else:
            print(f"\n✅ Received {event_count} events")
            return True

    except Exception as e:
        print(f"\n❌ Connection error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        sock.close()


if __name__ == "__main__":
    success = test_raw_sse()
    exit(0 if success else 1)
