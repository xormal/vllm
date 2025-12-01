# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project

import asyncio

import pytest

from vllm.entrypoints.openai.conversation_store import ConversationStore, ConversationNotFoundError
from vllm.entrypoints.openai.protocol import (
    ConversationCreateRequest,
    ConversationItemsCreateRequest,
    ConversationItemCreate,
    ConversationUpdateRequest,
)


@pytest.mark.asyncio
async def test_conversation_store_create_and_list_items():
    store = ConversationStore()
    convo = await store.create_conversation(
        ConversationCreateRequest(
            title="My convo",
            metadata={"topic": "tests"},
            items=[
                ConversationItemCreate(
                    role="user",
                    content=[{"type": "input_text", "text": "hello"}],
                )
            ],
        )
    )
    assert convo.title == "My convo"
    listing = await store.list_items(convo.id, limit=10, order="asc", after=None)
    assert listing.data
    assert listing.data[0].role == "user"


@pytest.mark.asyncio
async def test_conversation_store_update_and_add_items():
    store = ConversationStore()
    convo = await store.create_conversation(ConversationCreateRequest(title="temp"))
    updated = await store.update_conversation(
        convo.id, ConversationUpdateRequest(title="updated", status="archived")
    )
    assert updated.title == "updated"
    assert updated.status == "archived"
    created_items = await store.create_items(
        convo.id,
        ConversationItemsCreateRequest(
            items=[
                ConversationItemCreate(
                    role="assistant",
                    content=[{"type": "output_text", "text": "hi"}],
                )
            ]
        ),
    )
    assert len(created_items) == 1
    fetched = await store.get_item(convo.id, created_items[0].id)
    assert fetched.role == "assistant"


@pytest.mark.asyncio
async def test_conversation_store_delete_item_and_conversation():
    store = ConversationStore()
    convo = await store.create_conversation(ConversationCreateRequest())
    with pytest.raises(ConversationNotFoundError):
        await store.get_conversation("unknown")
    removed = await store.delete_item(convo.id, "missing")
    assert removed is False
    deleted = await store.delete_conversation(convo.id)
    assert deleted is True
