[DocsDocs](https://platform.openai.com/docs) [API referenceAPI](https://platform.openai.com/docs/api-reference/introduction)

Log in [Sign up](https://platform.openai.com/signup)

Search`` `K`

API Reference

[Introduction](https://platform.openai.com/docs/api-reference/introduction)

[Authentication](https://platform.openai.com/docs/api-reference/authentication)

[Debugging requests](https://platform.openai.com/docs/api-reference/debugging-requests)

[Backward compatibility](https://platform.openai.com/docs/api-reference/backward-compatibility)

Responses API

[Responses](https://platform.openai.com/docs/api-reference/responses)

[Conversations](https://platform.openai.com/docs/api-reference/conversations)

[Create a conversation](https://platform.openai.com/docs/api-reference/conversations/create)

[Retrieve a conversation](https://platform.openai.com/docs/api-reference/conversations/retrieve)

[Update a conversation](https://platform.openai.com/docs/api-reference/conversations/update)

[Delete a conversation](https://platform.openai.com/docs/api-reference/conversations/delete)

[List items](https://platform.openai.com/docs/api-reference/conversations/list-items)

[Create items](https://platform.openai.com/docs/api-reference/conversations/create-items)

[Retrieve an item](https://platform.openai.com/docs/api-reference/conversations/get-item)

[Delete an item](https://platform.openai.com/docs/api-reference/conversations/delete-item)

[The conversation object](https://platform.openai.com/docs/api-reference/conversations/object)

[The item list](https://platform.openai.com/docs/api-reference/conversations/list-items-object)

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

## Conversations

Create and manage conversations to store and retrieve conversation state across Response API calls.

## Create a conversation

posthttps://api.openai.com/v1/conversations

Create a conversation.

#### Request body

items

array

Optional

Initial items to include in the conversation context. You may add up to 20 items at a time.

Show possible types

metadata

object or null

Optional

Set of 16 key-value pairs that can be attached to an object. This can be useful for storing additional information about the object in a structured format, and querying for objects via API or the dashboard.
Keys are strings with a maximum length of 64 characters. Values are strings with a maximum length of 512 characters.

#### Returns

Returns a [Conversation](https://platform.openai.com/docs/api-reference/conversations/object) object.

Example request

curl

```bash
curl https://api.openai.com/v1/conversations \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -d '{
    "metadata": {"topic": "demo"},
    "items": [\
      {\
        "type": "message",\
        "role": "user",\
        "content": "Hello!"\
      }\
    ]
  }'
```

```javascript
import OpenAI from "openai";
const client = new OpenAI();

const conversation = await client.conversations.create({
  metadata: { topic: "demo" },
  items: [\
    { type: "message", role: "user", content: "Hello!" }\
  ],
});
console.log(conversation);
```

```python
from openai import OpenAI
client = OpenAI()

conversation = client.conversations.create(
  metadata={"topic": "demo"},
  items=[\
    {"type": "message", "role": "user", "content": "Hello!"}\
  ]
)
print(conversation)
```

```csharp
using System;
using System.Collections.Generic;
using OpenAI.Conversations;

OpenAIConversationClient client = new(
    apiKey: Environment.GetEnvironmentVariable("OPENAI_API_KEY")
);

Conversation conversation = client.CreateConversation(
    new CreateConversationOptions
    {
        Metadata = new Dictionary<string, string>
        {
            { "topic", "demo" }
        },
        Items =
        {
            new ConversationMessageInput
            {
                Role = "user",
                Content = "Hello!",
            }
        }
    }
);
Console.WriteLine(conversation.Id);
```

Response

```json
{
  "id": "conv_123",
  "object": "conversation",
  "created_at": 1741900000,
  "metadata": {"topic": "demo"}
}
```

## Retrieve a conversation

gethttps://api.openai.com/v1/conversations/{conversation\_id}

Get a conversation

#### Path parameters

conversation\_id

string

Required

The ID of the conversation to retrieve.

#### Returns

Returns a [Conversation](https://platform.openai.com/docs/api-reference/conversations/object) object.

Example request

curl

```bash
curl https://api.openai.com/v1/conversations/conv_123 \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

```javascript
import OpenAI from "openai";
const client = new OpenAI();

const conversation = await client.conversations.retrieve("conv_123");
console.log(conversation);
```

```python
from openai import OpenAI
client = OpenAI()

conversation = client.conversations.retrieve("conv_123")
print(conversation)
```

```csharp
using System;
using OpenAI.Conversations;

OpenAIConversationClient client = new(
    apiKey: Environment.GetEnvironmentVariable("OPENAI_API_KEY")
);

Conversation conversation = client.GetConversation("conv_123");
Console.WriteLine(conversation.Id);
```

Response

```json
{
  "id": "conv_123",
  "object": "conversation",
  "created_at": 1741900000,
  "metadata": {"topic": "demo"}
}
```

## Update a conversation

posthttps://api.openai.com/v1/conversations/{conversation\_id}

Update a conversation

#### Path parameters

conversation\_id

string

Required

The ID of the conversation to update.

#### Request body

metadata

map

Required

Set of 16 key-value pairs that can be attached to an object. This can be
useful for storing additional information about the object in a structured
format, and querying for objects via API or the dashboard.

Keys are strings with a maximum length of 64 characters. Values are strings
with a maximum length of 512 characters.

#### Returns

Returns the updated [Conversation](https://platform.openai.com/docs/api-reference/conversations/object) object.

Example request

curl

```bash
curl https://api.openai.com/v1/conversations/conv_123 \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -d '{
    "metadata": {"topic": "project-x"}
  }'
```

```javascript
import OpenAI from "openai";
const client = new OpenAI();

const updated = await client.conversations.update(
  "conv_123",
  { metadata: { topic: "project-x" } }
);
console.log(updated);
```

```python
from openai import OpenAI
client = OpenAI()

updated = client.conversations.update(
  "conv_123",
  metadata={"topic": "project-x"}
)
print(updated)
```

```csharp
using System;
using System.Collections.Generic;
using OpenAI.Conversations;

OpenAIConversationClient client = new(
    apiKey: Environment.GetEnvironmentVariable("OPENAI_API_KEY")
);

Conversation updated = client.UpdateConversation(
    conversationId: "conv_123",
    new UpdateConversationOptions
    {
        Metadata = new Dictionary<string, string>
        {
            { "topic", "project-x" }
        }
    }
);
Console.WriteLine(updated.Id);
```

Response

```json
{
  "id": "conv_123",
  "object": "conversation",
  "created_at": 1741900000,
  "metadata": {"topic": "project-x"}
}
```

## Delete a conversation

deletehttps://api.openai.com/v1/conversations/{conversation\_id}

Delete a conversation. Items in the conversation will not be deleted.

#### Path parameters

conversation\_id

string

Required

The ID of the conversation to delete.

#### Returns

A success message.

Example request

curl

```bash
curl -X DELETE https://api.openai.com/v1/conversations/conv_123 \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

```javascript
import OpenAI from "openai";
const client = new OpenAI();

const deleted = await client.conversations.delete("conv_123");
console.log(deleted);
```

```python
from openai import OpenAI
client = OpenAI()

deleted = client.conversations.delete("conv_123")
print(deleted)
```

```csharp
using System;
using OpenAI.Conversations;

OpenAIConversationClient client = new(
    apiKey: Environment.GetEnvironmentVariable("OPENAI_API_KEY")
);

DeletedConversation deleted = client.DeleteConversation("conv_123");
Console.WriteLine(deleted.Id);
```

Response

```json
{
  "id": "conv_123",
  "object": "conversation.deleted",
  "deleted": true
}
```

## List items

gethttps://api.openai.com/v1/conversations/{conversation\_id}/items

List all items for a conversation with the given ID.

#### Path parameters

conversation\_id

string

Required

The ID of the conversation to list items for.

#### Query parameters

after

string

Optional

An item ID to list items after, used in pagination.

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

Returns a [list object](https://platform.openai.com/docs/api-reference/conversations/list-items-object) containing Conversation items.

Example request

curl

```bash
curl "https://api.openai.com/v1/conversations/conv_123/items?limit=10" \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

```javascript
import OpenAI from "openai";
const client = new OpenAI();

const items = await client.conversations.items.list("conv_123", { limit: 10 });
console.log(items.data);
```

```python
from openai import OpenAI
client = OpenAI()

items = client.conversations.items.list("conv_123", limit=10)
print(items.data)
```

```csharp
using System;
using OpenAI.Conversations;

OpenAIConversationClient client = new(
    apiKey: Environment.GetEnvironmentVariable("OPENAI_API_KEY")
);

ConversationItemList items = client.ConversationItems.List(
    conversationId: "conv_123",
    new ListConversationItemsOptions { Limit = 10 }
);
Console.WriteLine(items.Data.Count);
```

Response

```json
{
  "object": "list",
  "data": [\
    {\
      "type": "message",\
      "id": "msg_abc",\
      "status": "completed",\
      "role": "user",\
      "content": [\
        {"type": "input_text", "text": "Hello!"}\
      ]\
    }\
  ],
  "first_id": "msg_abc",
  "last_id": "msg_abc",
  "has_more": false
}
```

## Create items

posthttps://api.openai.com/v1/conversations/{conversation\_id}/items

Create items in a conversation with the given ID.

#### Path parameters

conversation\_id

string

Required

The ID of the conversation to add the item to.

#### Query parameters

include

array

Optional

Additional fields to include in the response. See the `include`
parameter for [listing Conversation items above](https://platform.openai.com/docs/api-reference/conversations/list-items#conversations_list_items-include) for more information.

#### Request body

items

array

Required

The items to add to the conversation. You may add up to 20 items at a time.

Show possible types

#### Returns

Returns the list of added [items](https://platform.openai.com/docs/api-reference/conversations/list-items-object).

Example request

curl

```bash
curl https://api.openai.com/v1/conversations/conv_123/items \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -d '{
    "items": [\
      {\
        "type": "message",\
        "role": "user",\
        "content": [\
          {"type": "input_text", "text": "Hello!"}\
        ]\
      },\
      {\
        "type": "message",\
        "role": "user",\
        "content": [\
          {"type": "input_text", "text": "How are you?"}\
        ]\
      }\
    ]
  }'
```

```javascript
import OpenAI from "openai";
const client = new OpenAI();

const items = await client.conversations.items.create(
  "conv_123",
  {
    items: [\
      {\
        type: "message",\
        role: "user",\
        content: [{ type: "input_text", text: "Hello!" }],\
      },\
      {\
        type: "message",\
        role: "user",\
        content: [{ type: "input_text", text: "How are you?" }],\
      },\
    ],
  }
);
console.log(items.data);
```

```python
from openai import OpenAI
client = OpenAI()

items = client.conversations.items.create(
  "conv_123",
  items=[\
    {\
      "type": "message",\
      "role": "user",\
      "content": [{"type": "input_text", "text": "Hello!"}],\
    },\
    {\
      "type": "message",\
      "role": "user",\
      "content": [{"type": "input_text", "text": "How are you?"}],\
    }\
  ],
)
print(items.data)
```

```csharp
using System;
using System.Collections.Generic;
using OpenAI.Conversations;

OpenAIConversationClient client = new(
    apiKey: Environment.GetEnvironmentVariable("OPENAI_API_KEY")
);

ConversationItemList created = client.ConversationItems.Create(
    conversationId: "conv_123",
    new CreateConversationItemsOptions
    {
        Items = new List<ConversationItem>
        {
            new ConversationMessage
            {
                Role = "user",
                Content =
                {
                    new ConversationInputText { Text = "Hello!" }
                }
            },
            new ConversationMessage
            {
                Role = "user",
                Content =
                {
                    new ConversationInputText { Text = "How are you?" }
                }
            }
        }
    }
);
Console.WriteLine(created.Data.Count);
```

Response

```json
{
  "object": "list",
  "data": [\
    {\
      "type": "message",\
      "id": "msg_abc",\
      "status": "completed",\
      "role": "user",\
      "content": [\
        {"type": "input_text", "text": "Hello!"}\
      ]\
    },\
    {\
      "type": "message",\
      "id": "msg_def",\
      "status": "completed",\
      "role": "user",\
      "content": [\
        {"type": "input_text", "text": "How are you?"}\
      ]\
    }\
  ],
  "first_id": "msg_abc",
  "last_id": "msg_def",
  "has_more": false
}
```

## Retrieve an item

gethttps://api.openai.com/v1/conversations/{conversation\_id}/items/{item\_id}

Get a single item from a conversation with the given IDs.

#### Path parameters

conversation\_id

string

Required

The ID of the conversation that contains the item.

item\_id

string

Required

The ID of the item to retrieve.

#### Query parameters

include

array

Optional

Additional fields to include in the response. See the `include`
parameter for [listing Conversation items above](https://platform.openai.com/docs/api-reference/conversations/list-items#conversations_list_items-include) for more information.

#### Returns

Returns a [Conversation Item](https://platform.openai.com/docs/api-reference/conversations/item-object).

Example request

curl

```bash
curl https://api.openai.com/v1/conversations/conv_123/items/msg_abc \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

```javascript
import OpenAI from "openai";
const client = new OpenAI();

const item = await client.conversations.items.retrieve(
  "conv_123",
  "msg_abc"
);
console.log(item);
```

```python
from openai import OpenAI
client = OpenAI()

item = client.conversations.items.retrieve("conv_123", "msg_abc")
print(item)
```

```csharp
using System;
using OpenAI.Conversations;

OpenAIConversationClient client = new(
    apiKey: Environment.GetEnvironmentVariable("OPENAI_API_KEY")
);

ConversationItem item = client.ConversationItems.Get(
    conversationId: "conv_123",
    itemId: "msg_abc"
);
Console.WriteLine(item.Id);
```

Response

```json
{
  "type": "message",
  "id": "msg_abc",
  "status": "completed",
  "role": "user",
  "content": [\
    {"type": "input_text", "text": "Hello!"}\
  ]
}
```

## Delete an item

deletehttps://api.openai.com/v1/conversations/{conversation\_id}/items/{item\_id}

Delete an item from a conversation with the given IDs.

#### Path parameters

conversation\_id

string

Required

The ID of the conversation that contains the item.

item\_id

string

Required

The ID of the item to delete.

#### Returns

Returns the updated [Conversation](https://platform.openai.com/docs/api-reference/conversations/object) object.

Example request

curl

```bash
curl -X DELETE https://api.openai.com/v1/conversations/conv_123/items/msg_abc \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

```javascript
import OpenAI from "openai";
const client = new OpenAI();

const conversation = await client.conversations.items.delete(
  "conv_123",
  "msg_abc"
);
console.log(conversation);
```

```python
from openai import OpenAI
client = OpenAI()

conversation = client.conversations.items.delete("conv_123", "msg_abc")
print(conversation)
```

```csharp
using System;
using OpenAI.Conversations;

OpenAIConversationClient client = new(
    apiKey: Environment.GetEnvironmentVariable("OPENAI_API_KEY")
);

Conversation conversation = client.ConversationItems.Delete(
    conversationId: "conv_123",
    itemId: "msg_abc"
);
Console.WriteLine(conversation.Id);
```

Response

```json
{
  "id": "conv_123",
  "object": "conversation",
  "created_at": 1741900000,
  "metadata": {"topic": "demo"}
}
```

## The conversation object

created\_at

integer

The time at which the conversation was created, measured in seconds since the Unix epoch.

id

string

The unique ID of the conversation.

metadata

Set of 16 key-value pairs that can be attached to an object. This can be useful for storing additional information about the object in a structured format, and querying for objects via API or the dashboard.
Keys are strings with a maximum length of 64 characters. Values are strings with a maximum length of 512 characters.

object

string

The object type, which is always `conversation`.

## The item list

A list of Conversation items.

data

array

A list of conversation items.

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

[PreviousResponses](https://platform.openai.com/docs/api-reference/responses) [NextStreaming events](https://platform.openai.com/docs/api-reference/responses-streaming)