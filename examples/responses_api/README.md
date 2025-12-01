# Responses API Code Samples

This directory contains runnable snippets that exercise the `/v1/responses`
endpoint using the `openai` Python SDK (>= 1.3.0). Each example assumes the
server is running locally at `http://localhost:8000/v1` without authentication.

## 1. Basic Streaming Chat

```python
import asyncio
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="EMPTY",  # Not required for local deployments
)

async def main():
    stream = await client.responses.stream(
        model="gpt-4o-mini",
        input="Summarize the repository layout.",
        stream=True,
    )
    async for event in stream:
        if event.type == "response.output_text.delta":
            print(event.delta["content"][0]["text"], end="", flush=True)
        if event.type == "response.completed":
            break

asyncio.run(main())
```

## 2. Tool Call Workflow

```python
import asyncio
import json
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="EMPTY")

async def main():
    # Step 1: initiate streaming response with tools
    stream = await client.responses.stream(
        model="gpt-4o-mini",
        input="Get system time.",
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "get_time",
                    "description": "Return current time.",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
        stream=True,
    )

    response_id = None
    tool_call_id = None
    async for event in stream:
        if event.type == "response.created":
            response_id = event.response["id"]
        if event.type == "response.tool_call.delta":
            chunk = json.loads(event.delta)
            if chunk:
                tool_call_id = chunk[0]["id"]
            break

    # Step 2: send tool output back to the server
    await client.responses.submit_tool_outputs(
        response_id=response_id,
        tool_call_id=tool_call_id,
        output=[{"type": "output_text", "text": "It is 18:42 UTC."}],
    )

    # Optional: fetch final response
    result = await client.responses.retrieve(response_id=response_id)
    print(result.output[0]["content"][0]["text"])

asyncio.run(main())
```

## 3. Background Jobs with GET Polling

```python
from openai import OpenAI
import time

client = OpenAI(base_url="http://localhost:8000/v1", api_key="EMPTY")

resp = client.responses.create(
    model="gpt-4o-mini",
    input="Run a long analysis.",
    background=True,
    store=True,
)
print("Queued:", resp.status, resp.id)

while True:
    stored = client.responses.retrieve(resp.id)
    print("Status:", stored.status)
    if stored.status == "completed":
        print("Output:", stored.output[0]["content"][0]["text"])
        break
    time.sleep(1)
```

## Running the Examples

```bash
pip install openai>=1.3 asyncio httpx
python examples/responses_api/basic_stream.py
```

> Note: For production, use real API keys and HTTPS endpoints. Adjust the code to
> handle heartbeats (`response.ping`) and `Retry-After` headers if you connect to
> a remote deployment.
