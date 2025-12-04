## Responses /compact endpoint (server side)

Current Telegram compact requests fail with `405 Method Not Allowed` on `POST /v1/responses/compact`. To support manual `/compact` and auto-compact:

### Endpoint
- `POST /v1/responses/compact`

### Request (OpenAI Responses-compatible)
```json
{
  "model": "<provider model>",
  "input": [
    {
      "type": "message",
      "role": "user",
      "content": [
        { "type": "input_text", "text": "<conversation text to compact>" }
      ]
    }
  ],
  "instructions": "Summarize conversation history to reduce context size.",
  "stream": false
}
```

### Response
```
200 OK
{
  "id": "resp_<id>",
  "object": "response",
  "created": <ts>,
  "model": "<model>",
  "output": [
    {
      "type": "message",
      "role": "assistant",
      "content": [
        { "type": "output_text", "text": "<compacted summary>" }
      ]
    }
  ],
  "usage": {
    "input_tokens": <i64>,
    "output_tokens": <i64>,
    "total_tokens": <i64>
  }
}
```

### Token counting helper
- Add an endpoint to return token counts for a given Responses payload (used to trigger auto-compact thresholds):
  - `POST /v1/responses/tokenize`
  - Body mirrors `responses` request; reply includes `usage` as above.

### Error handling
- Non-2xx returns JSON `{ "error": { "message": "..." } }` per OpenAI style.

### Notes
- Compact should reuse the same auth/model routing as regular `/v1/responses` calls.
- Token counting can be shared with the streaming path; cache tokenizer per model to avoid recompute.
