[DocsDocs](https://platform.openai.com/docs/guides/text-generation) [API referenceAPI](https://platform.openai.com/docs/api-reference/introduction)

Log in [Sign up](https://platform.openai.com/signup)

Search`` `K`

API Reference

[Introduction](https://platform.openai.com/docs/api-reference/introduction)

[Authentication](https://platform.openai.com/docs/api-reference/authentication)

[Debugging requests](https://platform.openai.com/docs/api-reference/debugging-requests)

[Backward compatibility](https://platform.openai.com/docs/api-reference/backward-compatibility)

Responses API

[Responses](https://platform.openai.com/docs/api-reference/responses)

[Create a model response](https://platform.openai.com/docs/api-reference/responses/create)

[Get a model response](https://platform.openai.com/docs/api-reference/responses/get)

[Delete a model response](https://platform.openai.com/docs/api-reference/responses/delete)

[Cancel a response](https://platform.openai.com/docs/api-reference/responses/cancel)

[List input items](https://platform.openai.com/docs/api-reference/responses/input-items)

[Get input token counts](https://platform.openai.com/docs/api-reference/responses/input-tokens)

[The response object](https://platform.openai.com/docs/api-reference/responses/object)

[The input item list](https://platform.openai.com/docs/api-reference/responses/list)

[Conversations](https://platform.openai.com/docs/api-reference/conversations)

[Streaming events](https://platform.openai.com/docs/api-reference/responses-streaming)

Webhooks

[Webhook Events](https://platform.openai.com/docs/api-reference/webhook-events)

Platform APIs

[Audio](https://platform.openai.com/docs/api-reference/audio)

[Videos](https://platform.openai.com/docs/api-reference/videos)

[Images](https://platform.openai.com/docs/api-reference/images)

[Image Streaming](https://platform.openai.com/docs/api-reference/images-streaming)

[Embeddings](https://platform.openai.com/docs/api-reference/embeddings)

[Evals](https://platform.openai.com/docs/api-reference/evals)

[Fine-tuning](https://platform.openai.com/docs/api-reference/fine-tuning)

[Graders](https://platform.openai.com/docs/api-reference/graders)

[Batch](https://platform.openai.com/docs/api-reference/batch)

[Files](https://platform.openai.com/docs/api-reference/files)

[Uploads](https://platform.openai.com/docs/api-reference/uploads)

[Models](https://platform.openai.com/docs/api-reference/models)

[Moderations](https://platform.openai.com/docs/api-reference/moderations)

Vector stores

[Vector stores](https://platform.openai.com/docs/api-reference/vector-stores)

[Vector store files](https://platform.openai.com/docs/api-reference/vector-stores-files)

[Vector store file batches](https://platform.openai.com/docs/api-reference/vector-stores-file-batches)

ChatKit

Beta

[ChatKit](https://platform.openai.com/docs/api-reference/chatkit)

Containers

[Containers](https://platform.openai.com/docs/api-reference/containers)

[Container Files](https://platform.openai.com/docs/api-reference/container-files)

Realtime

[Realtime](https://platform.openai.com/docs/api-reference/realtime)

[Client secrets](https://platform.openai.com/docs/api-reference/realtime-sessions)

[Calls](https://platform.openai.com/docs/api-reference/realtime-calls)

[Client events](https://platform.openai.com/docs/api-reference/realtime-client-events)

[Server events](https://platform.openai.com/docs/api-reference/realtime-server-events)

Chat Completions

[Chat Completions](https://platform.openai.com/docs/api-reference/chat)

[Streaming](https://platform.openai.com/docs/api-reference/chat-streaming)

Assistants

Beta

[Assistants](https://platform.openai.com/docs/api-reference/assistants)

[Threads](https://platform.openai.com/docs/api-reference/threads)

[Messages](https://platform.openai.com/docs/api-reference/messages)

[Runs](https://platform.openai.com/docs/api-reference/runs)

[Run steps](https://platform.openai.com/docs/api-reference/run-steps)

[Streaming](https://platform.openai.com/docs/api-reference/assistants-streaming)

Administration

[Administration](https://platform.openai.com/docs/api-reference/administration)

[Admin API Keys](https://platform.openai.com/docs/api-reference/admin-api-keys)

[Invites](https://platform.openai.com/docs/api-reference/invite)

[Users](https://platform.openai.com/docs/api-reference/users)

[Groups](https://platform.openai.com/docs/api-reference/groups)

[Roles](https://platform.openai.com/docs/api-reference/roles)

[Role assignments](https://platform.openai.com/docs/api-reference/role-assignments)

[Projects](https://platform.openai.com/docs/api-reference/projects)

[Project users](https://platform.openai.com/docs/api-reference/project-users)

[Project groups](https://platform.openai.com/docs/api-reference/project-groups)

[Project service accounts](https://platform.openai.com/docs/api-reference/project-service-accounts)

[Project API keys](https://platform.openai.com/docs/api-reference/project-api-keys)

[Project rate limits](https://platform.openai.com/docs/api-reference/project-rate-limits)

[Audit logs](https://platform.openai.com/docs/api-reference/audit-logs)

[Usage](https://platform.openai.com/docs/api-reference/usage)

[Certificates](https://platform.openai.com/docs/api-reference/certificates)

Legacy

[Completions](https://platform.openai.com/docs/api-reference/completions)

[Realtime Beta](https://platform.openai.com/docs/api-reference/realtime_beta)

[Realtime Beta session tokens](https://platform.openai.com/docs/api-reference/realtime-beta-sessions)

[Realtime Beta client events](https://platform.openai.com/docs/api-reference/realtime-beta-client-events)

[Realtime Beta server events](https://platform.openai.com/docs/api-reference/realtime-beta-server-events)

[Cookbook](https://cookbook.openai.com/) [Forum](https://community.openai.com/categories)

## Responses

OpenAI's most advanced interface for generating model responses. Supports
text and image inputs, and text outputs. Create stateful interactions
with the model, using the output of previous responses as input. Extend
the model's capabilities with built-in tools for file search, web search,
computer use, and more. Allow the model access to external systems and data
using function calling.

Related guides:

- [Quickstart](https://platform.openai.com/docs/quickstart?api-mode=responses)
- [Text inputs and outputs](https://platform.openai.com/docs/guides/text?api-mode=responses)
- [Image inputs](https://platform.openai.com/docs/guides/images?api-mode=responses)
- [Structured Outputs](https://platform.openai.com/docs/guides/structured-outputs?api-mode=responses)
- [Function calling](https://platform.openai.com/docs/guides/function-calling?api-mode=responses)
- [Conversation state](https://platform.openai.com/docs/guides/conversation-state?api-mode=responses)
- [Extend the models with tools](https://platform.openai.com/docs/guides/tools?api-mode=responses)

## Create a model response

posthttps://api.openai.com/v1/responses

Creates a model response. Provide [text](https://platform.openai.com/docs/guides/text) or
[image](https://platform.openai.com/docs/guides/images) inputs to generate [text](https://platform.openai.com/docs/guides/text)
or [JSON](https://platform.openai.com/docs/guides/structured-outputs) outputs. Have the model call
your own [custom code](https://platform.openai.com/docs/guides/function-calling) or use built-in
[tools](https://platform.openai.com/docs/guides/tools) like [web search](https://platform.openai.com/docs/guides/tools-web-search)
or [file search](https://platform.openai.com/docs/guides/tools-file-search) to use your own data
as input for the model's response.

#### Request body

background

boolean

Optional

Defaults to false

Whether to run the model response in the background.
[Learn more](https://platform.openai.com/docs/guides/background).

conversation

string or object

Optional

Defaults to null

The conversation that this response belongs to. Items from this conversation are prepended to `input_items` for this response request.
Input items and output items from this response are automatically added to this conversation after this response completes.

Show possible types

include

array

Optional

Specify additional output data to include in the model response. Currently supported values are:

- `web_search_call.action.sources`: Include the sources of the web search tool call.
- `code_interpreter_call.outputs`: Includes the outputs of python code execution in code interpreter tool call items.
- `computer_call_output.output.image_url`: Include image urls from the computer call output.
- `file_search_call.results`: Include the search results of the file search tool call.
- `message.input_image.image_url`: Include image urls from the input message.
- `message.output_text.logprobs`: Include logprobs with assistant messages.
- `reasoning.encrypted_content`: Includes an encrypted version of reasoning tokens in reasoning item outputs. This enables reasoning items to be used in multi-turn conversations when using the Responses API statelessly (like when the `store` parameter is set to `false`, or when an organization is enrolled in the zero data retention program).

input

string or array

Optional

Text, image, or file inputs to the model, used to generate a response.

Learn more:

- [Text inputs and outputs](https://platform.openai.com/docs/guides/text)
- [Image inputs](https://platform.openai.com/docs/guides/images)
- [File inputs](https://platform.openai.com/docs/guides/pdf-files)
- [Conversation state](https://platform.openai.com/docs/guides/conversation-state)
- [Function calling](https://platform.openai.com/docs/guides/function-calling)

Show possible types

instructions

string

Optional

A system (or developer) message inserted into the model's context.

When using along with `previous_response_id`, the instructions from a previous
response will not be carried over to the next response. This makes it simple
to swap out system (or developer) messages in new responses.

max\_output\_tokens

integer

Optional

An upper bound for the number of tokens that can be generated for a response, including visible output tokens and [reasoning tokens](https://platform.openai.com/docs/guides/reasoning).

max\_tool\_calls

integer

Optional

The maximum number of total calls to built-in tools that can be processed in a response. This maximum number applies across all built-in tool calls, not per individual tool. Any further attempts to call a tool by the model will be ignored.

metadata

map

Optional

Set of 16 key-value pairs that can be attached to an object. This can be
useful for storing additional information about the object in a structured
format, and querying for objects via API or the dashboard.

Keys are strings with a maximum length of 64 characters. Values are strings
with a maximum length of 512 characters.

model

string

Optional

Model ID used to generate the response, like `gpt-4o` or `o3`. OpenAI
offers a wide range of models with different capabilities, performance
characteristics, and price points. Refer to the [model guide](https://platform.openai.com/docs/models)
to browse and compare available models.

parallel\_tool\_calls

boolean

Optional

Defaults to true

Whether to allow the model to run tool calls in parallel.

previous\_response\_id

string

Optional

The unique ID of the previous response to the model. Use this to
create multi-turn conversations. Learn more about
[conversation state](https://platform.openai.com/docs/guides/conversation-state). Cannot be used in conjunction with `conversation`.

prompt

object

Optional

Reference to a prompt template and its variables.
[Learn more](https://platform.openai.com/docs/guides/text?api-mode=responses#reusable-prompts).

Show properties

prompt\_cache\_key

string

Optional

Used by OpenAI to cache responses for similar requests to optimize your cache hit rates. Replaces the `user` field. [Learn more](https://platform.openai.com/docs/guides/prompt-caching).

prompt\_cache\_retention

string

Optional

The retention policy for the prompt cache. Set to `24h` to enable extended prompt caching, which keeps cached prefixes active for longer, up to a maximum of 24 hours. [Learn more](https://platform.openai.com/docs/guides/prompt-caching#prompt-cache-retention).

reasoning

object

Optional

**gpt-5 and o-series models only**

Configuration options for
[reasoning models](https://platform.openai.com/docs/guides/reasoning).

Show properties

safety\_identifier

string

Optional

A stable identifier used to help detect users of your application that may be violating OpenAI's usage policies.
The IDs should be a string that uniquely identifies each user. We recommend hashing their username or email address, in order to avoid sending us any identifying information. [Learn more](https://platform.openai.com/docs/guides/safety-best-practices#safety-identifiers).

service\_tier

string

Optional

Defaults to auto

Specifies the processing type used for serving the request.

- If set to 'auto', then the request will be processed with the service tier configured in the Project settings. Unless otherwise configured, the Project will use 'default'.
- If set to 'default', then the request will be processed with the standard pricing and performance for the selected model.
- If set to ' [flex](https://platform.openai.com/docs/guides/flex-processing)' or ' [priority](https://openai.com/api-priority-processing/)', then the request will be processed with the corresponding service tier.
- When not set, the default behavior is 'auto'.

When the `service_tier` parameter is set, the response body will include the `service_tier` value based on the processing mode actually used to serve the request. This response value may be different from the value set in the parameter.

store

boolean

Optional

Defaults to true

Whether to store the generated model response for later retrieval via
API.

stream

boolean

Optional

Defaults to false

If set to true, the model response data will be streamed to the client
as it is generated using [server-sent events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events#Event_stream_format).
See the [Streaming section below](https://platform.openai.com/docs/api-reference/responses-streaming)
for more information.

stream\_options

object

Optional

Defaults to null

Options for streaming responses. Only set this when you set `stream: true`.

Show properties

temperature

number

Optional

Defaults to 1

What sampling temperature to use, between 0 and 2. Higher values like 0.8 will make the output more random, while lower values like 0.2 will make it more focused and deterministic.
We generally recommend altering this or `top_p` but not both.

text

object

Optional

Configuration options for a text response from the model. Can be plain
text or structured JSON data. Learn more:

- [Text inputs and outputs](https://platform.openai.com/docs/guides/text)
- [Structured Outputs](https://platform.openai.com/docs/guides/structured-outputs)

Show properties

tool\_choice

string or object

Optional

How the model should select which tool (or tools) to use when generating
a response. See the `tools` parameter to see how to specify which tools
the model can call.

Show possible types

tools

array

Optional

An array of tools the model may call while generating a response. You
can specify which tool to use by setting the `tool_choice` parameter.

We support the following categories of tools:

- **Built-in tools**: Tools that are provided by OpenAI that extend the
model's capabilities, like [web search](https://platform.openai.com/docs/guides/tools-web-search)
or [file search](https://platform.openai.com/docs/guides/tools-file-search). Learn more about
[built-in tools](https://platform.openai.com/docs/guides/tools).
- **MCP Tools**: Integrations with third-party systems via custom MCP servers
or predefined connectors such as Google Drive and SharePoint. Learn more about
[MCP Tools](https://platform.openai.com/docs/guides/tools-connectors-mcp).
- **Function calls (custom tools)**: Functions that are defined by you,
enabling the model to call your own code with strongly typed arguments
and outputs. Learn more about
[function calling](https://platform.openai.com/docs/guides/function-calling). You can also use
custom tools to call your own code.

Show possible types

top\_logprobs

integer

Optional

An integer between 0 and 20 specifying the number of most likely tokens to
return at each token position, each with an associated log probability.

top\_p

number

Optional

Defaults to 1

An alternative to sampling with temperature, called nucleus sampling,
where the model considers the results of the tokens with top\_p probability
mass. So 0.1 means only the tokens comprising the top 10% probability mass
are considered.

We generally recommend altering this or `temperature` but not both.

truncation

string

Optional

Defaults to disabled

The truncation strategy to use for the model response.

- `auto`: If the input to this Response exceeds
the model's context window size, the model will truncate the
response to fit the context window by dropping items from the beginning of the conversation.
- `disabled` (default): If the input size will exceed the context window
size for a model, the request will fail with a 400 error.

user

Deprecated

string

Optional

This field is being replaced by `safety_identifier` and `prompt_cache_key`. Use `prompt_cache_key` instead to maintain caching optimizations.
A stable identifier for your end-users.
Used to boost cache hit rates by better bucketing similar requests and to help OpenAI detect and prevent abuse. [Learn more](https://platform.openai.com/docs/guides/safety-best-practices#safety-identifiers).

#### Returns

Returns a [Response](https://platform.openai.com/docs/api-reference/responses/object) object.

Text inputImage inputFile inputWeb searchFile searchStreamingFunctionsReasoning

Example request

curl

```bash
curl https://api.openai.com/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -d '{
    "model": "gpt-4.1",
    "input": "Tell me a three sentence bedtime story about a unicorn."
  }'
```

```javascript
import OpenAI from "openai";

const openai = new OpenAI();

const response = await openai.responses.create({
    model: "gpt-4.1",
    input: "Tell me a three sentence bedtime story about a unicorn."
});

console.log(response);
```

```python
from openai import OpenAI

client = OpenAI()

response = client.responses.create(
  model="gpt-4.1",
  input="Tell me a three sentence bedtime story about a unicorn."
)

print(response)
```

```csharp
using System;
using OpenAI.Responses;

OpenAIResponseClient client = new(
    model: "gpt-4.1",
    apiKey: Environment.GetEnvironmentVariable("OPENAI_API_KEY")
);

OpenAIResponse response = client.CreateResponse("Tell me a three sentence bedtime story about a unicorn.");

Console.WriteLine(response.GetOutputText());
```

Response

```json
{
  "id": "resp_67ccd2bed1ec8190b14f964abc0542670bb6a6b452d3795b",
  "object": "response",
  "created_at": 1741476542,
  "status": "completed",
  "error": null,
  "incomplete_details": null,
  "instructions": null,
  "max_output_tokens": null,
  "model": "gpt-4.1-2025-04-14",
  "output": [\
    {\
      "type": "message",\
      "id": "msg_67ccd2bf17f0819081ff3bb2cf6508e60bb6a6b452d3795b",\
      "status": "completed",\
      "role": "assistant",\
      "content": [\
        {\
          "type": "output_text",\
          "text": "In a peaceful grove beneath a silver moon, a unicorn named Lumina discovered a hidden pool that reflected the stars. As she dipped her horn into the water, the pool began to shimmer, revealing a pathway to a magical realm of endless night skies. Filled with wonder, Lumina whispered a wish for all who dream to find their own hidden magic, and as she glanced back, her hoofprints sparkled like stardust.",\
          "annotations": []\
        }\
      ]\
    }\
  ],
  "parallel_tool_calls": true,
  "previous_response_id": null,
  "reasoning": {
    "effort": null,
    "summary": null
  },
  "store": true,
  "temperature": 1.0,
  "text": {
    "format": {
      "type": "text"
    }
  },
  "tool_choice": "auto",
  "tools": [],
  "top_p": 1.0,
  "truncation": "disabled",
  "usage": {
    "input_tokens": 36,
    "input_tokens_details": {
      "cached_tokens": 0
    },
    "output_tokens": 87,
    "output_tokens_details": {
      "reasoning_tokens": 0
    },
    "total_tokens": 123
  },
  "user": null,
  "metadata": {}
}
```

## Get a model response

gethttps://api.openai.com/v1/responses/{response\_id}

Retrieves a model response with the given ID.

#### Path parameters

response\_id

string

Required

The ID of the response to retrieve.

#### Query parameters

include

array

Optional

Additional fields to include in the response. See the `include`
parameter for Response creation above for more information.

include\_obfuscation

boolean

Optional

When true, stream obfuscation will be enabled. Stream obfuscation adds
random characters to an `obfuscation` field on streaming delta events
to normalize payload sizes as a mitigation to certain side-channel
attacks. These obfuscation fields are included by default, but add a
small amount of overhead to the data stream. You can set
`include_obfuscation` to false to optimize for bandwidth if you trust
the network links between your application and the OpenAI API.

starting\_after

integer

Optional

The sequence number of the event after which to start streaming.

stream

boolean

Optional

If set to true, the model response data will be streamed to the client
as it is generated using [server-sent events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events#Event_stream_format).
See the [Streaming section below](https://platform.openai.com/docs/api-reference/responses-streaming)
for more information.

#### Returns

The [Response](https://platform.openai.com/docs/api-reference/responses/object) object matching the
specified ID.

Example request

curl

```bash
curl https://api.openai.com/v1/responses/resp_123 \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $OPENAI_API_KEY"
```

```javascript
import OpenAI from "openai";
const client = new OpenAI();

const response = await client.responses.retrieve("resp_123");
console.log(response);
```

```python
from openai import OpenAI
client = OpenAI()

response = client.responses.retrieve("resp_123")
print(response)
```

Response

```json
{
  "id": "resp_67cb71b351908190a308f3859487620d06981a8637e6bc44",
  "object": "response",
  "created_at": 1741386163,
  "status": "completed",
  "error": null,
  "incomplete_details": null,
  "instructions": null,
  "max_output_tokens": null,
  "model": "gpt-4o-2024-08-06",
  "output": [\
    {\
      "type": "message",\
      "id": "msg_67cb71b3c2b0819084d481baaaf148f206981a8637e6bc44",\
      "status": "completed",\
      "role": "assistant",\
      "content": [\
        {\
          "type": "output_text",\
          "text": "Silent circuits hum,  \nThoughts emerge in data streams—  \nDigital dawn breaks.",\
          "annotations": []\
        }\
      ]\
    }\
  ],
  "parallel_tool_calls": true,
  "previous_response_id": null,
  "reasoning": {
    "effort": null,
    "summary": null
  },
  "store": true,
  "temperature": 1.0,
  "text": {
    "format": {
      "type": "text"
    }
  },
  "tool_choice": "auto",
  "tools": [],
  "top_p": 1.0,
  "truncation": "disabled",
  "usage": {
    "input_tokens": 32,
    "input_tokens_details": {
      "cached_tokens": 0
    },
    "output_tokens": 18,
    "output_tokens_details": {
      "reasoning_tokens": 0
    },
    "total_tokens": 50
  },
  "user": null,
  "metadata": {}
}
```

## Delete a model response

deletehttps://api.openai.com/v1/responses/{response\_id}

Deletes a model response with the given ID.

#### Path parameters

response\_id

string

Required

The ID of the response to delete.

#### Returns

A success message.

Example request

curl

```bash
curl -X DELETE https://api.openai.com/v1/responses/resp_123 \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $OPENAI_API_KEY"
```

```javascript
import OpenAI from "openai";
const client = new OpenAI();

const response = await client.responses.delete("resp_123");
console.log(response);
```

```python
from openai import OpenAI
client = OpenAI()

response = client.responses.delete("resp_123")
print(response)
```

Response

```json
{
  "id": "resp_6786a1bec27481909a17d673315b29f6",
  "object": "response",
  "deleted": true
}
```

## Cancel a response

posthttps://api.openai.com/v1/responses/{response\_id}/cancel

Cancels a model response with the given ID. Only responses created with
the `background` parameter set to `true` can be cancelled.
[Learn more](https://platform.openai.com/docs/guides/background).

#### Path parameters

response\_id

string

Required

The ID of the response to cancel.

#### Returns

A [Response](https://platform.openai.com/docs/api-reference/responses/object) object.

Example request

curl

```bash
curl -X POST https://api.openai.com/v1/responses/resp_123/cancel \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $OPENAI_API_KEY"
```

```javascript
import OpenAI from "openai";
const client = new OpenAI();

const response = await client.responses.cancel("resp_123");
console.log(response);
```

```python
from openai import OpenAI
client = OpenAI()

response = client.responses.cancel("resp_123")
print(response)
```

Response

```json
{
  "id": "resp_67cb71b351908190a308f3859487620d06981a8637e6bc44",
  "object": "response",
  "created_at": 1741386163,
  "status": "completed",
  "error": null,
  "incomplete_details": null,
  "instructions": null,
  "max_output_tokens": null,
  "model": "gpt-4o-2024-08-06",
  "output": [\
    {\
      "type": "message",\
      "id": "msg_67cb71b3c2b0819084d481baaaf148f206981a8637e6bc44",\
      "status": "completed",\
      "role": "assistant",\
      "content": [\
        {\
          "type": "output_text",\
          "text": "Silent circuits hum,  \nThoughts emerge in data streams—  \nDigital dawn breaks.",\
          "annotations": []\
        }\
      ]\
    }\
  ],
  "parallel_tool_calls": true,
  "previous_response_id": null,
  "reasoning": {
    "effort": null,
    "summary": null
  },
  "store": true,
  "temperature": 1.0,
  "text": {
    "format": {
      "type": "text"
    }
  },
  "tool_choice": "auto",
  "tools": [],
  "top_p": 1.0,
  "truncation": "disabled",
  "usage": {
    "input_tokens": 32,
    "input_tokens_details": {
      "cached_tokens": 0
    },
    "output_tokens": 18,
    "output_tokens_details": {
      "reasoning_tokens": 0
    },
    "total_tokens": 50
  },
  "user": null,
  "metadata": {}
}
```

## List input items

gethttps://api.openai.com/v1/responses/{response\_id}/input\_items

Returns a list of input items for a given response.

#### Path parameters

response\_id

string

Required

The ID of the response to retrieve input items for.

#### Query parameters

after

string

Optional

An item ID to list items after, used in pagination.

include

array

Optional

Additional fields to include in the response. See the `include`
parameter for Response creation above for more information.

limit

integer

Optional

Defaults to 20

A limit on the number of objects to be returned. Limit can range between
1 and 100, and the default is 20.

order

string

Optional

The order to return the input items in. Default is `desc`.

- `asc`: Return the input items in ascending order.
- `desc`: Return the input items in descending order.

#### Returns

A list of input item objects.

Example request

curl

```bash
curl https://api.openai.com/v1/responses/resp_abc123/input_items \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

```javascript
import OpenAI from "openai";
const client = new OpenAI();

const response = await client.responses.inputItems.list("resp_123");
console.log(response.data);
```

```python
from openai import OpenAI
client = OpenAI()

response = client.responses.input_items.list("resp_123")
print(response.data)
```

Response

```json
{
  "object": "list",
  "data": [\
    {\
      "id": "msg_abc123",\
      "type": "message",\
      "role": "user",\
      "content": [\
        {\
          "type": "input_text",\
          "text": "Tell me a three sentence bedtime story about a unicorn."\
        }\
      ]\
    }\
  ],
  "first_id": "msg_abc123",
  "last_id": "msg_abc123",
  "has_more": false
}
```

## Get input token counts

posthttps://api.openai.com/v1/responses/input\_tokens

Get input token counts

#### Request body

conversation

string or object

Optional

Defaults to null

The conversation that this response belongs to. Items from this conversation are prepended to `input_items` for this response request.
Input items and output items from this response are automatically added to this conversation after this response completes.

Show possible types

input

string or array

Optional

Text, image, or file inputs to the model, used to generate a response

Show possible types

instructions

string

Optional

A system (or developer) message inserted into the model's context.
When used along with `previous_response_id`, the instructions from a previous response will not be carried over to the next response. This makes it simple to swap out system (or developer) messages in new responses.

model

string

Optional

Model ID used to generate the response, like `gpt-4o` or `o3`. OpenAI offers a wide range of models with different capabilities, performance characteristics, and price points. Refer to the [model guide](https://platform.openai.com/docs/models) to browse and compare available models.

parallel\_tool\_calls

boolean

Optional

Whether to allow the model to run tool calls in parallel.

previous\_response\_id

string

Optional

The unique ID of the previous response to the model. Use this to create multi-turn conversations. Learn more about [conversation state](https://platform.openai.com/docs/guides/conversation-state). Cannot be used in conjunction with `conversation`.

reasoning

object

Optional

**gpt-5 and o-series models only**

Configuration options for
[reasoning models](https://platform.openai.com/docs/guides/reasoning).

Show properties

text

object

Optional

Configuration options for a text response from the model. Can be plain
text or structured JSON data. Learn more:

- [Text inputs and outputs](https://platform.openai.com/docs/guides/text)
- [Structured Outputs](https://platform.openai.com/docs/guides/structured-outputs)

Show properties

tool\_choice

string or object

Optional

How the model should select which tool (or tools) to use when generating
a response. See the `tools` parameter to see how to specify which tools
the model can call.

Show possible types

tools

array

Optional

An array of tools the model may call while generating a response. You can specify which tool to use by setting the `tool_choice` parameter.

Show possible types

truncation

string

Optional

The truncation strategy to use for the model response. - `auto`: If the input to this Response exceeds the model's context window size, the model will truncate the response to fit the context window by dropping items from the beginning of the conversation. - `disabled` (default): If the input size will exceed the context window size for a model, the request will fail with a 400 error.

#### Returns

The input token counts.

```json
{
  object: "response.input_tokens"
  input_tokens: 123
}
```

Example request

curl

```bash
curl -X POST https://api.openai.com/v1/responses/input_tokens \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $OPENAI_API_KEY" \
    -d '{
      "model": "gpt-5",
      "input": "Tell me a joke."
    }'
```

```javascript
import OpenAI from "openai";

const client = new OpenAI();

const response = await client.responses.inputTokens.count({
  model: "gpt-5",
  input: "Tell me a joke.",
});

console.log(response.input_tokens);
```

```python
from openai import OpenAI

client = OpenAI()

response = client.responses.input_tokens.count(
    model="gpt-5",
    input="Tell me a joke."
)
print(response.input_tokens)
```

```go
package main

import (
  "context"
  "fmt"

  "github.com/openai/openai-go"
  "github.com/openai/openai-go/responses"
)

func main() {
  client := openai.NewClient()
  response, err := client.Responses.InputTokens.Count(context.TODO(), responses.InputTokenCountParams{
    Model: "gpt-5",
    Input: "Tell me a joke.",
  })
  if err != nil {
    panic(err.Error())
  }
  fmt.Printf("%+v\n", response.InputTokens)
}
```

```java
package com.openai.example;

import com.openai.client.OpenAIClient;
import com.openai.client.okhttp.OpenAIOkHttpClient;
import com.openai.models.responses.inputtokens.InputTokenCountParams;
import com.openai.models.responses.inputtokens.InputTokenCountResponse;

public final class Main {
    private Main() {}

    public static void main(String[] args) {
        OpenAIClient client = OpenAIOkHttpClient.fromEnv();

        InputTokenCountParams params = InputTokenCountParams.builder()
            .model("gpt-5")
            .input("Tell me a joke.")
            .build();

        InputTokenCountResponse response = client.responses().inputTokens().count(params);
    }
}
```

```ruby
require "openai"

openai = OpenAI::Client.new

response = openai.responses.input_tokens.count(model: "gpt-5", input: "Tell me a joke.")

puts(response)
```

Response

```json
{
  "object": "response.input_tokens",
  "input_tokens": 11
}
```

## The response object

background

boolean

Whether to run the model response in the background.
[Learn more](https://platform.openai.com/docs/guides/background).

conversation

object

The conversation that this response belongs to. Input items and output items from this response are automatically added to this conversation.

Show properties

created\_at

number

Unix timestamp (in seconds) of when this Response was created.

error

object

An error object returned when the model fails to generate a Response.

Show properties

id

string

Unique identifier for this Response.

incomplete\_details

object

Details about why the response is incomplete.

Show properties

instructions

string or array

A system (or developer) message inserted into the model's context.

When using along with `previous_response_id`, the instructions from a previous
response will not be carried over to the next response. This makes it simple
to swap out system (or developer) messages in new responses.

Show possible types

max\_output\_tokens

integer

An upper bound for the number of tokens that can be generated for a response, including visible output tokens and [reasoning tokens](https://platform.openai.com/docs/guides/reasoning).

max\_tool\_calls

integer

The maximum number of total calls to built-in tools that can be processed in a response. This maximum number applies across all built-in tool calls, not per individual tool. Any further attempts to call a tool by the model will be ignored.

metadata

map

Set of 16 key-value pairs that can be attached to an object. This can be
useful for storing additional information about the object in a structured
format, and querying for objects via API or the dashboard.

Keys are strings with a maximum length of 64 characters. Values are strings
with a maximum length of 512 characters.

model

string

Model ID used to generate the response, like `gpt-4o` or `o3`. OpenAI
offers a wide range of models with different capabilities, performance
characteristics, and price points. Refer to the [model guide](https://platform.openai.com/docs/models)
to browse and compare available models.

object

string

The object type of this resource - always set to `response`.

output

array

An array of content items generated by the model.

- The length and order of items in the `output` array is dependent
on the model's response.
- Rather than accessing the first item in the `output` array and
assuming it's an `assistant` message with the content generated by
the model, you might consider using the `output_text` property where
supported in SDKs.

Show possible types

output\_text

string

SDK Only

SDK-only convenience property that contains the aggregated text output
from all `output_text` items in the `output` array, if any are present.
Supported in the Python and JavaScript SDKs.

parallel\_tool\_calls

boolean

Whether to allow the model to run tool calls in parallel.

previous\_response\_id

string

The unique ID of the previous response to the model. Use this to
create multi-turn conversations. Learn more about
[conversation state](https://platform.openai.com/docs/guides/conversation-state). Cannot be used in conjunction with `conversation`.

prompt

object

Reference to a prompt template and its variables.
[Learn more](https://platform.openai.com/docs/guides/text?api-mode=responses#reusable-prompts).

Show properties

prompt\_cache\_key

string

Used by OpenAI to cache responses for similar requests to optimize your cache hit rates. Replaces the `user` field. [Learn more](https://platform.openai.com/docs/guides/prompt-caching).

prompt\_cache\_retention

string

The retention policy for the prompt cache. Set to `24h` to enable extended prompt caching, which keeps cached prefixes active for longer, up to a maximum of 24 hours. [Learn more](https://platform.openai.com/docs/guides/prompt-caching#prompt-cache-retention).

reasoning

object

**gpt-5 and o-series models only**

Configuration options for
[reasoning models](https://platform.openai.com/docs/guides/reasoning).

Show properties

safety\_identifier

string

A stable identifier used to help detect users of your application that may be violating OpenAI's usage policies.
The IDs should be a string that uniquely identifies each user. We recommend hashing their username or email address, in order to avoid sending us any identifying information. [Learn more](https://platform.openai.com/docs/guides/safety-best-practices#safety-identifiers).

service\_tier

string

Specifies the processing type used for serving the request.

- If set to 'auto', then the request will be processed with the service tier configured in the Project settings. Unless otherwise configured, the Project will use 'default'.
- If set to 'default', then the request will be processed with the standard pricing and performance for the selected model.
- If set to ' [flex](https://platform.openai.com/docs/guides/flex-processing)' or ' [priority](https://openai.com/api-priority-processing/)', then the request will be processed with the corresponding service tier.
- When not set, the default behavior is 'auto'.

When the `service_tier` parameter is set, the response body will include the `service_tier` value based on the processing mode actually used to serve the request. This response value may be different from the value set in the parameter.

status

string

The status of the response generation. One of `completed`, `failed`,
`in_progress`, `cancelled`, `queued`, or `incomplete`.

temperature

number

What sampling temperature to use, between 0 and 2. Higher values like 0.8 will make the output more random, while lower values like 0.2 will make it more focused and deterministic.
We generally recommend altering this or `top_p` but not both.

text

object

Configuration options for a text response from the model. Can be plain
text or structured JSON data. Learn more:

- [Text inputs and outputs](https://platform.openai.com/docs/guides/text)
- [Structured Outputs](https://platform.openai.com/docs/guides/structured-outputs)

Show properties

tool\_choice

string or object

How the model should select which tool (or tools) to use when generating
a response. See the `tools` parameter to see how to specify which tools
the model can call.

Show possible types

tools

array

An array of tools the model may call while generating a response. You
can specify which tool to use by setting the `tool_choice` parameter.

We support the following categories of tools:

- **Built-in tools**: Tools that are provided by OpenAI that extend the
model's capabilities, like [web search](https://platform.openai.com/docs/guides/tools-web-search)
or [file search](https://platform.openai.com/docs/guides/tools-file-search). Learn more about
[built-in tools](https://platform.openai.com/docs/guides/tools).
- **MCP Tools**: Integrations with third-party systems via custom MCP servers
or predefined connectors such as Google Drive and SharePoint. Learn more about
[MCP Tools](https://platform.openai.com/docs/guides/tools-connectors-mcp).
- **Function calls (custom tools)**: Functions that are defined by you,
enabling the model to call your own code with strongly typed arguments
and outputs. Learn more about
[function calling](https://platform.openai.com/docs/guides/function-calling). You can also use
custom tools to call your own code.

Show possible types

top\_logprobs

integer

An integer between 0 and 20 specifying the number of most likely tokens to
return at each token position, each with an associated log probability.

top\_p

number

An alternative to sampling with temperature, called nucleus sampling,
where the model considers the results of the tokens with top\_p probability
mass. So 0.1 means only the tokens comprising the top 10% probability mass
are considered.

We generally recommend altering this or `temperature` but not both.

truncation

string

The truncation strategy to use for the model response.

- `auto`: If the input to this Response exceeds
the model's context window size, the model will truncate the
response to fit the context window by dropping items from the beginning of the conversation.
- `disabled` (default): If the input size will exceed the context window
size for a model, the request will fail with a 400 error.

usage

object

Represents token usage details including input tokens, output tokens,
a breakdown of output tokens, and the total tokens used.

Show properties

user

Deprecated

string

This field is being replaced by `safety_identifier` and `prompt_cache_key`. Use `prompt_cache_key` instead to maintain caching optimizations.
A stable identifier for your end-users.
Used to boost cache hit rates by better bucketing similar requests and to help OpenAI detect and prevent abuse. [Learn more](https://platform.openai.com/docs/guides/safety-best-practices#safety-identifiers).

OBJECT The response object

```json
{
  "id": "resp_67ccd3a9da748190baa7f1570fe91ac604becb25c45c1d41",
  "object": "response",
  "created_at": 1741476777,
  "status": "completed",
  "error": null,
  "incomplete_details": null,
  "instructions": null,
  "max_output_tokens": null,
  "model": "gpt-4o-2024-08-06",
  "output": [\
    {\
      "type": "message",\
      "id": "msg_67ccd3acc8d48190a77525dc6de64b4104becb25c45c1d41",\
      "status": "completed",\
      "role": "assistant",\
      "content": [\
        {\
          "type": "output_text",\
          "text": "The image depicts a scenic landscape with a wooden boardwalk or pathway leading through lush, green grass under a blue sky with some clouds. The setting suggests a peaceful natural area, possibly a park or nature reserve. There are trees and shrubs in the background.",\
          "annotations": []\
        }\
      ]\
    }\
  ],
  "parallel_tool_calls": true,
  "previous_response_id": null,
  "reasoning": {
    "effort": null,
    "summary": null
  },
  "store": true,
  "temperature": 1,
  "text": {
    "format": {
      "type": "text"
    }
  },
  "tool_choice": "auto",
  "tools": [],
  "top_p": 1,
  "truncation": "disabled",
  "usage": {
    "input_tokens": 328,
    "input_tokens_details": {
      "cached_tokens": 0
    },
    "output_tokens": 52,
    "output_tokens_details": {
      "reasoning_tokens": 0
    },
    "total_tokens": 380
  },
  "user": null,
  "metadata": {}
}
```

## The input item list

A list of Response items.

data

array

A list of items used to generate this response.

Show possible types

first\_id

string

The ID of the first item in the list.

has\_more

boolean

Whether there are more items available.

last\_id

string

The ID of the last item in the list.

object

string

The type of object returned, must be `list`.

OBJECT The input item list

```json
{
  "object": "list",
  "data": [\
    {\
      "id": "msg_abc123",\
      "type": "message",\
      "role": "user",\
      "content": [\
        {\
          "type": "input_text",\
          "text": "Tell me a three sentence bedtime story about a unicorn."\
        }\
      ]\
    }\
  ],
  "first_id": "msg_abc123",
  "last_id": "msg_abc123",
  "has_more": false
}
```

[PreviousIntroduction](https://platform.openai.com/docs/api-reference/introduction) [NextConversations](https://platform.openai.com/docs/api-reference/conversations)