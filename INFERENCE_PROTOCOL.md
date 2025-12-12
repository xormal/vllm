# Mistral Vibe Inference Server Protocol

This document describes the protocol used by Mistral Vibe to communicate with LLM inference servers (Mistral AI API and OpenAI-compatible APIs).

## Table of Contents

1. [Protocol Overview](#protocol-overview)
2. [API Endpoints](#api-endpoints)
3. [Message Format](#message-format)
4. [Tool Integration](#tool-integration)
5. [Streaming Responses](#streaming-responses)
6. [MCP Tools Integration](#mcp-tools-integration)
7. [Implementation Details](#implementation-details)
8. [Complete Examples](#complete-examples)

---

## Protocol Overview

### Architecture

Mistral Vibe communicates with inference servers using the **OpenAI Chat Completions API** format. It supports two backend implementations:

1. **Mistral Backend**: Native Mistral AI SDK (mistralai Python package)
2. **Generic Backend**: OpenAI-compatible HTTP API

```
┌─────────────────────────┐
│   Mistral Vibe Agent    │
│                         │
│  - Core Agent           │
│  - Tool Manager         │
│  - Format Handler       │
└────────┬────────────────┘
         │
         │ Chat Completions API
         │ (OpenAI format)
         │
         ▼
┌─────────────────────────┐
│  Inference Server       │
│                         │
│  - Mistral API          │
│  - OpenAI API           │
│  - llama.cpp server     │
│  - Other compatible     │
└─────────────────────────┘
```

### Supported Servers

**Mistral AI** (official):
- Endpoint: `https://api.mistral.ai/v1`
- Models: `mistral-vibe-cli-latest`, `devstral-small-latest`, etc.

**Local Servers**:
- llama.cpp server: `http://127.0.0.1:8080/v1`
- Other OpenAI-compatible servers

### Configuration

```toml
# ~/.vibe/config.toml

[[providers]]
name = "mistral"
api_base = "https://api.mistral.ai/v1"
api_key_env_var = "MISTRAL_API_KEY"
backend = "mistral"  # or "generic"

[[models]]
name = "mistral-vibe-cli-latest"
provider = "mistral"
alias = "devstral-2"
temperature = 0.2
input_price = 0.4    # USD per million input tokens
output_price = 2.0   # USD per million output tokens
```

---

## API Endpoints

### Chat Completions Endpoint

**URL**: `/chat/completions`

**Method**: `POST`

**Full URL**: `{api_base}/chat/completions`

Example: `https://api.mistral.ai/v1/chat/completions`

---

## Message Format

### Request Structure

```json
{
  "model": "mistral-vibe-cli-latest",
  "messages": [
    {
      "role": "system",
      "content": "You are a helpful coding assistant..."
    },
    {
      "role": "user",
      "content": "Create a hello world function"
    }
  ],
  "temperature": 0.2,
  "max_tokens": null,
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "write_file",
        "description": "Write content to a file",
        "parameters": {
          "type": "object",
          "properties": {
            "path": {
              "type": "string",
              "description": "Path to the file"
            },
            "content": {
              "type": "string",
              "description": "File content"
            }
          },
          "required": ["path", "content"]
        }
      }
    }
  ],
  "tool_choice": "auto",
  "stream": false
}
```

### Request Fields

#### Required Fields

- **`model`** (string): Model identifier
  - Example: `"mistral-vibe-cli-latest"`

- **`messages`** (array): Conversation history
  - Array of message objects (see Message Types below)

#### Optional Fields

- **`temperature`** (float): Sampling temperature (0.0 - 1.0)
  - Default: `0.2`
  - Lower = more deterministic, Higher = more creative

- **`max_tokens`** (integer | null): Maximum completion tokens
  - Default: `null` (no limit)

- **`tools`** (array | null): Available tools/functions
  - Array of tool definitions (see Tool Format below)

- **`tool_choice`** (string | object | null): Tool selection strategy
  - `"auto"`: Model decides whether to call tools (default)
  - `"none"`: Model will not call any tools
  - `"any"` / `"required"`: Model must call at least one tool
  - Object: Force specific tool (see below)

- **`stream`** (boolean): Enable streaming responses
  - `true`: Server-Sent Events (SSE) stream
  - `false`: Single JSON response (default)

- **`stream_options`** (object): Streaming configuration (Mistral only)
  - `{"stream_tool_calls": true}`: Enable tool call streaming

### Message Types

#### 1. System Message

```json
{
  "role": "system",
  "content": "You are a helpful coding assistant with access to file system tools..."
}
```

**Purpose**: Provide instructions and context to the model.

#### 2. User Message

```json
{
  "role": "user",
  "content": "Create a Python function that prints hello world"
}
```

**Purpose**: User input/request.

#### 3. Assistant Message (with content)

```json
{
  "role": "assistant",
  "content": "I'll create a hello world function for you."
}
```

**Purpose**: Model's text response.

#### 4. Assistant Message (with tool calls)

```json
{
  "role": "assistant",
  "content": "I'll write the function to a file.",
  "tool_calls": [
    {
      "id": "call_abc123",
      "type": "function",
      "index": 0,
      "function": {
        "name": "write_file",
        "arguments": "{\"path\":\"hello.py\",\"content\":\"def hello():\\n    print('Hello, World!')\\n\"}"
      }
    }
  ]
}
```

**Purpose**: Model requests tool execution.

**Fields**:
- `tool_calls`: Array of tool call objects
  - `id`: Unique identifier for this tool call
  - `type`: Always `"function"`
  - `index`: Call index (for parallel calls)
  - `function`: Function call details
    - `name`: Tool name
    - `arguments`: JSON-encoded arguments string

#### 5. Tool Message

```json
{
  "role": "tool",
  "tool_call_id": "call_abc123",
  "name": "write_file",
  "content": "{\"success\":true,\"path\":\"hello.py\"}"
}
```

**Purpose**: Tool execution result.

**Fields**:
- `tool_call_id`: Must match the tool call's `id`
- `name`: Tool name
- `content`: Result (typically JSON string)

### Tool Choice Formats

#### String Choices

```json
{
  "tool_choice": "auto"
}
```

**Values**:
- `"auto"`: Model decides
- `"none"`: No tools
- `"any"` / `"required"`: Must use tools

#### Forced Tool Choice

```json
{
  "tool_choice": {
    "type": "function",
    "function": {
      "name": "write_file"
    }
  }
}
```

**Purpose**: Force model to use specific tool.

---

## Tool Integration

### Tool Definition Format

Tools are defined using **JSON Schema** for function parameters.

```json
{
  "type": "function",
  "function": {
    "name": "write_file",
    "description": "Write content to a file at the specified path",
    "parameters": {
      "type": "object",
      "properties": {
        "path": {
          "type": "string",
          "description": "Path to the file (relative or absolute)"
        },
        "content": {
          "type": "string",
          "description": "Content to write to the file"
        }
      },
      "required": ["path", "content"],
      "additionalProperties": false
    }
  }
}
```

### Tool Definition Fields

- **`type`**: Always `"function"`
- **`function`**: Function definition
  - **`name`** (string): Unique tool identifier
    - Must match tool class name in Vibe
    - Example: `"write_file"`, `"read_file"`, `"bash"`
  - **`description`** (string): Human-readable description
    - Used by LLM to understand when to use the tool
    - Should be clear and concise
  - **`parameters`** (object): JSON Schema for arguments
    - **`type`**: Always `"object"`
    - **`properties`**: Argument definitions (JSON Schema)
    - **`required`**: Array of required argument names
    - **`additionalProperties`**: Usually `false`

### Tool Format Handler

Vibe uses `APIToolFormatHandler` to convert internal tool definitions to API format:

```python
# vibe/core/llm/format.py
class APIToolFormatHandler:
    def get_available_tools(
        self, tool_manager: ToolManager, config: VibeConfig
    ) -> list[AvailableTool]:
        active_tools = get_active_tool_classes(tool_manager, config)

        return [
            AvailableTool(
                function=AvailableFunction(
                    name=tool_class.get_name(),
                    description=tool_class.description,
                    parameters=tool_class.get_parameters(),
                )
            )
            for tool_class in active_tools
        ]
```

**Conversion**:
1. Get active tools from `ToolManager`
2. Extract name, description, parameters from each tool class
3. Build `AvailableTool` objects in API format
4. Send to inference server

---

## Streaming Responses

### Enabling Streaming

**Request**:
```json
{
  "model": "mistral-vibe-cli-latest",
  "messages": [...],
  "tools": [...],
  "stream": true,
  "stream_options": {
    "stream_tool_calls": true
  }
}
```

### Response Format (SSE)

Streaming responses use **Server-Sent Events** (SSE) format:

```
data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1677652288,"model":"mistral-vibe-cli-latest","choices":[{"index":0,"delta":{"role":"assistant","content":""},"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1677652288,"model":"mistral-vibe-cli-latest","choices":[{"index":0,"delta":{"content":"I'll"},"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1677652288,"model":"mistral-vibe-cli-latest","choices":[{"index":0,"delta":{"content":" create"},"finish_reason":null}]}

data: [DONE]
```

### Chunk Structure

Each chunk is a JSON object with:

```typescript
{
  "id": string;           // Completion ID
  "object": string;       // "chat.completion.chunk"
  "created": number;      // Unix timestamp
  "model": string;        // Model name
  "choices": [
    {
      "index": number;    // Choice index (usually 0)
      "delta": {
        "role"?: "assistant";
        "content"?: string;      // Incremental text content
        "tool_calls"?: [         // Incremental tool calls
          {
            "index": number;
            "id"?: string;
            "type"?: "function";
            "function"?: {
              "name"?: string;
              "arguments"?: string;  // Partial JSON arguments
            }
          }
        ]
      };
      "finish_reason": string | null;  // "stop", "tool_calls", null
    }
  ];
  "usage"?: {
    "prompt_tokens": number;
    "completion_tokens": number;
  }
}
```

### Streaming Tool Calls

Tool calls are streamed incrementally:

```
data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_abc123","type":"function","function":{"name":"write_file","arguments":""}}]}}]}

data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{\\"path"}}]}}]}

data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"\\":"}}]}}]}

data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"\\"hello.py\\""}}]}}]}

data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":","}}]}}]}

data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"\\"content\\":\\""}}]}}]}

...

data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}],"usage":{"prompt_tokens":123,"completion_tokens":45}}

data: [DONE]
```

**Note**: Arguments are streamed character-by-character and must be concatenated to form valid JSON.

### Non-Streaming Response

**Response**:
```json
{
  "id": "chatcmpl-123",
  "object": "chat.completion",
  "created": 1677652288,
  "model": "mistral-vibe-cli-latest",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "I'll write the function to a file.",
        "tool_calls": [
          {
            "id": "call_abc123",
            "type": "function",
            "index": 0,
            "function": {
              "name": "write_file",
              "arguments": "{\"path\":\"hello.py\",\"content\":\"def hello():\\n    print('Hello, World!')\\n\"}"
            }
          }
        ]
      },
      "finish_reason": "tool_calls"
    }
  ],
  "usage": {
    "prompt_tokens": 123,
    "completion_tokens": 45
  }
}
```

### Finish Reasons

- **`"stop"`**: Model completed naturally
- **`"tool_calls"`**: Model wants to call tools
- **`"length"`**: Max tokens reached
- **`null`**: Streaming in progress (not finished)

---

## MCP Tools Integration

### How MCP Tools Are Exposed to LLM

Mistral Vibe **integrates MCP tools seamlessly** with the inference server protocol:

1. **Tool Discovery**: `ToolManager` discovers MCP tools via `list_tools` (see MCP_PROTOCOL.md)
2. **Format Conversion**: `APIToolFormatHandler` converts MCP tools to API format
3. **API Transmission**: Tools sent to inference server in `tools` array
4. **LLM Selection**: Model sees MCP tools alongside built-in tools
5. **Tool Execution**: When model calls an MCP tool, Vibe executes it via MCP protocol
6. **Result Return**: Tool result sent back to LLM in next request

### Example: MCP Tool in API Request

**MCP Server Configuration**:
```toml
[[mcp_servers]]
name = "weather"
transport = "http"
url = "http://localhost:8000"
```

**MCP Tool Definition** (from server):
```json
{
  "name": "get_weather",
  "description": "Get current weather for a location",
  "inputSchema": {
    "type": "object",
    "properties": {
      "location": {
        "type": "string",
        "description": "City name or coordinates"
      },
      "units": {
        "type": "string",
        "enum": ["celsius", "fahrenheit"],
        "default": "celsius"
      }
    },
    "required": ["location"]
  }
}
```

**Converted to API Format**:
```json
{
  "type": "function",
  "function": {
    "name": "weather_get_weather",
    "description": "Get current weather for a location",
    "parameters": {
      "type": "object",
      "properties": {
        "location": {
          "type": "string",
          "description": "City name or coordinates"
        },
        "units": {
          "type": "string",
          "enum": ["celsius", "fahrenheit"],
          "default": "celsius"
        }
      },
      "required": ["location"]
    }
  }
}
```

**Note**: Tool name is prefixed with MCP server alias (`weather_get_weather`).

### MCP Tool Execution Flow

```
1. User: "What's the weather in Paris?"
        │
        ▼
2. Vibe sends to LLM:
   POST /chat/completions
   {
     "messages": [...],
     "tools": [
       {"function": {"name": "weather_get_weather", ...}},
       {"function": {"name": "write_file", ...}},
       ...
     ]
   }
        │
        ▼
3. LLM responds:
   {
     "choices": [{
       "message": {
         "tool_calls": [{
           "function": {
             "name": "weather_get_weather",
             "arguments": "{\"location\":\"Paris\"}"
           }
         }]
       }
     }]
   }
        │
        ▼
4. Vibe executes MCP tool:
   - Recognizes "weather_get_weather" as MCP tool
   - Calls MCP server via tools/call
   - Receives: {"temperature": 18, "conditions": "sunny"}
        │
        ▼
5. Vibe sends result to LLM:
   POST /chat/completions
   {
     "messages": [
       ...,
       {
         "role": "assistant",
         "tool_calls": [...]
       },
       {
         "role": "tool",
         "tool_call_id": "call_123",
         "name": "weather_get_weather",
         "content": "{\"temperature\":18,\"conditions\":\"sunny\"}"
       }
     ]
   }
        │
        ▼
6. LLM responds with final answer:
   {
     "choices": [{
       "message": {
         "content": "The weather in Paris is 18°C and sunny."
       }
     }]
   }
```

### MCP Tools Are Transparent to LLM

**Key Point**: The LLM (inference server) **does not know** that some tools are from MCP servers. From the LLM's perspective:

- All tools are presented in the same OpenAI format
- Tool calls use the same mechanism
- Tool results have the same structure

**Vibe handles**:
- MCP tool discovery and registration
- Name prefixing for uniqueness
- Protocol translation (OpenAI ↔ MCP)
- Execution routing (built-in vs MCP)

---

## Implementation Details

### Mistral Backend

Uses official `mistralai` Python SDK:

```python
# vibe/core/llm/backend/mistral.py
class MistralBackend:
    async def complete_streaming(
        self,
        *,
        model: ModelConfig,
        messages: list[LLMMessage],
        temperature: float,
        tools: list[AvailableTool] | None,
        max_tokens: int | None,
        tool_choice: StrToolChoice | AvailableTool | None,
        extra_headers: dict[str, str] | None,
    ) -> AsyncGenerator[LLMChunk, None]:
        async for chunk in await self._get_client().chat.stream_async(
            model=model.name,
            messages=[self._mapper.prepare_message(msg) for msg in messages],
            temperature=temperature,
            tools=[self._mapper.prepare_tool(tool) for tool in tools]
            if tools
            else None,
            max_tokens=max_tokens,
            tool_choice=self._mapper.prepare_tool_choice(tool_choice)
            if tool_choice
            else None,
            http_headers=extra_headers,
        ):
            yield LLMChunk(...)
```

**Features**:
- Native SDK integration
- Automatic retry and error handling
- Type-safe API calls

### Generic Backend (OpenAI-compatible)

Uses `httpx` for HTTP requests:

```python
# vibe/core/llm/backend/generic.py
class GenericBackend:
    async def complete_streaming(
        self, ...
    ) -> AsyncGenerator[LLMChunk, None]:
        adapter = BACKEND_ADAPTERS["openai"]  # OpenAIAdapter

        endpoint, headers, body = adapter.prepare_request(
            model_name=model.name,
            messages=messages,
            temperature=temperature,
            tools=tools,
            max_tokens=max_tokens,
            tool_choice=tool_choice,
            enable_streaming=True,
            provider=self._provider,
            api_key=api_key,
        )

        url = f"{self._provider.api_base}{endpoint}"

        async for res_data in self._make_streaming_request(url, body, headers):
            yield adapter.parse_response(res_data)
```

**Features**:
- HTTP/HTTPS support
- SSE parsing
- OpenAI-compatible format
- Retry mechanism

### SSE Parsing

```python
async def _make_streaming_request(
    self, url: str, data: bytes, headers: dict[str, str]
) -> AsyncGenerator[dict[str, Any]]:
    async with client.stream(
        method="POST", url=url, content=data, headers=headers
    ) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            if line.strip() == "":
                continue

            # Parse SSE format: "data: {...}"
            delim_index = line.find(":")
            key = line[0:delim_index]
            value = line[delim_index + 2 :]

            if key != "data":
                continue
            if value == "[DONE]":
                return

            yield json.loads(value.strip())
```

### Tool Call Resolution

```python
# vibe/core/llm/format.py
class APIToolFormatHandler:
    def resolve_tool_calls(
        self, parsed: ParsedMessage, tool_manager: ToolManager, config: VibeConfig
    ) -> ResolvedMessage:
        resolved_calls = []
        failed_calls = []

        active_tools = {
            tool_class.get_name(): tool_class
            for tool_class in get_active_tool_classes(tool_manager, config)
        }

        for parsed_call in parsed.tool_calls:
            tool_class = active_tools.get(parsed_call.tool_name)
            if not tool_class:
                failed_calls.append(
                    FailedToolCall(
                        tool_name=parsed_call.tool_name,
                        call_id=parsed_call.call_id,
                        error=f"Unknown tool '{parsed_call.tool_name}'"
                    )
                )
                continue

            # Validate arguments against tool schema
            args_model, _ = tool_class._get_tool_args_results()
            try:
                validated_args = args_model.model_validate(parsed_call.raw_args)
                resolved_calls.append(ResolvedToolCall(...))
            except ValidationError as e:
                failed_calls.append(
                    FailedToolCall(
                        tool_name=parsed_call.tool_name,
                        call_id=parsed_call.call_id,
                        error=f"Invalid arguments: {e}"
                    )
                )

        return ResolvedMessage(tool_calls=resolved_calls, failed_calls=failed_calls)
```

---

## Complete Examples

### Example 1: Simple Completion (No Tools)

**Request**:
```http
POST https://api.mistral.ai/v1/chat/completions
Content-Type: application/json
Authorization: Bearer sk-xxx...

{
  "model": "mistral-vibe-cli-latest",
  "messages": [
    {
      "role": "system",
      "content": "You are a helpful assistant."
    },
    {
      "role": "user",
      "content": "What is 2+2?"
    }
  ],
  "temperature": 0.2,
  "stream": false
}
```

**Response**:
```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1677652288,
  "model": "mistral-vibe-cli-latest",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "2 + 2 equals 4."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 25,
    "completion_tokens": 8
  }
}
```

### Example 2: Tool Call (Built-in)

**Request**:
```http
POST https://api.mistral.ai/v1/chat/completions
Content-Type: application/json
Authorization: Bearer sk-xxx...

{
  "model": "mistral-vibe-cli-latest",
  "messages": [
    {
      "role": "system",
      "content": "You are a coding assistant with file system access."
    },
    {
      "role": "user",
      "content": "Create a file hello.py with a hello world function"
    }
  ],
  "temperature": 0.2,
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "write_file",
        "description": "Write content to a file",
        "parameters": {
          "type": "object",
          "properties": {
            "path": {
              "type": "string",
              "description": "File path"
            },
            "content": {
              "type": "string",
              "description": "File content"
            }
          },
          "required": ["path", "content"]
        }
      }
    }
  ],
  "tool_choice": "auto",
  "stream": false
}
```

**Response**:
```json
{
  "id": "chatcmpl-def456",
  "object": "chat.completion",
  "created": 1677652300,
  "model": "mistral-vibe-cli-latest",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "I'll create the hello.py file for you.",
        "tool_calls": [
          {
            "id": "call_abc123",
            "type": "function",
            "index": 0,
            "function": {
              "name": "write_file",
              "arguments": "{\"path\":\"hello.py\",\"content\":\"def hello():\\n    print('Hello, World!')\\n\"}"
            }
          }
        ]
      },
      "finish_reason": "tool_calls"
    }
  ],
  "usage": {
    "prompt_tokens": 150,
    "completion_tokens": 45
  }
}
```

**Next Request** (with tool result):
```json
{
  "model": "mistral-vibe-cli-latest",
  "messages": [
    {
      "role": "system",
      "content": "You are a coding assistant with file system access."
    },
    {
      "role": "user",
      "content": "Create a file hello.py with a hello world function"
    },
    {
      "role": "assistant",
      "content": "I'll create the hello.py file for you.",
      "tool_calls": [
        {
          "id": "call_abc123",
          "type": "function",
          "index": 0,
          "function": {
            "name": "write_file",
            "arguments": "{\"path\":\"hello.py\",\"content\":\"def hello():\\n    print('Hello, World!')\\n\"}"
          }
        }
      ]
    },
    {
      "role": "tool",
      "tool_call_id": "call_abc123",
      "name": "write_file",
      "content": "{\"success\":true,\"path\":\"hello.py\"}"
    }
  ],
  "temperature": 0.2
}
```

**Final Response**:
```json
{
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": "I've successfully created hello.py with a hello world function."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 200,
    "completion_tokens": 15
  }
}
```

### Example 3: MCP Tool Call

**MCP Tool** (from weather server):
- Name: `get_weather`
- Registered as: `weather_get_weather`

**Request**:
```json
{
  "model": "mistral-vibe-cli-latest",
  "messages": [
    {
      "role": "user",
      "content": "What's the weather in Paris?"
    }
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "weather_get_weather",
        "description": "Get current weather for a location",
        "parameters": {
          "type": "object",
          "properties": {
            "location": {"type": "string"}
          },
          "required": ["location"]
        }
      }
    }
  ],
  "tool_choice": "auto"
}
```

**Response**:
```json
{
  "choices": [
    {
      "message": {
        "role": "assistant",
        "tool_calls": [
          {
            "id": "call_789",
            "function": {
              "name": "weather_get_weather",
              "arguments": "{\"location\":\"Paris\"}"
            }
          }
        ]
      },
      "finish_reason": "tool_calls"
    }
  ]
}
```

**Vibe's Action**:
1. Recognizes `weather_get_weather` as MCP tool
2. Calls MCP server: `tools/call` with `{"name": "get_weather", "arguments": {"location": "Paris"}}`
3. Receives: `{"content": [{"type": "text", "text": "18°C, sunny"}]}`

**Next Request**:
```json
{
  "messages": [
    ...,
    {
      "role": "tool",
      "tool_call_id": "call_789",
      "name": "weather_get_weather",
      "content": "18°C, sunny"
    }
  ]
}
```

**Final Response**:
```json
{
  "choices": [
    {
      "message": {
        "content": "The weather in Paris is currently 18°C and sunny."
      }
    }
  ]
}
```

---

## Summary

### Protocol Characteristics

- **Standard**: OpenAI Chat Completions API
- **Transport**: HTTP/HTTPS with JSON
- **Streaming**: Server-Sent Events (SSE)
- **Tool Format**: OpenAI function calling
- **Authentication**: Bearer token (API key)

### MCP Integration

**Confirmation**: ✅ **MCP tools ARE fully integrated with the inference protocol**

**How**:
1. MCP tools discovered via MCP protocol
2. Converted to OpenAI tool format
3. Sent to LLM alongside built-in tools
4. LLM treats them identically
5. Vibe routes execution based on tool name prefix

**Transparency**:
- LLM doesn't know which tools are MCP-based
- Same request/response format for all tools
- Vibe handles protocol translation internally

### Key Takeaways

1. **Unified Tool Interface**: All tools (built-in, MCP, custom) use the same API format
2. **OpenAI Compatibility**: Works with any OpenAI-compatible server
3. **Streaming Support**: Real-time responses with SSE
4. **Type Safety**: Pydantic validation for all requests/responses
5. **MCP Transparency**: MCP tools seamlessly integrated without special LLM support

---

## References

- **Mistral AI API**: https://docs.mistral.ai/api
- **Function Calling**: https://docs.mistral.ai/capabilities/function_calling
- **OpenAI API**: https://platform.openai.com/docs/api-reference/chat
- **Vibe Backend Code**:
  - `vibe/core/llm/backend/mistral.py`
  - `vibe/core/llm/backend/generic.py`
  - `vibe/core/llm/format.py`

---

**End of Inference Server Protocol Documentation**
