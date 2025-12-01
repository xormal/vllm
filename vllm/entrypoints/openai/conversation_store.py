# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from typing import Any

from vllm.entrypoints.openai.protocol import (
    ConversationCreateRequest,
    ConversationItem,
    ConversationItemCreate,
    ConversationItemsCreateRequest,
    ConversationListItemsResponse,
    ConversationObject,
    ConversationUpdateRequest,
)
from vllm.utils import random_uuid


class ConversationNotFoundError(KeyError):
    """Raised when a conversation cannot be found."""


class ConversationStore:
    """In-memory conversation storage used by the Conversations API."""

    def __init__(self, max_conversations: int = 1000):
        self._lock = asyncio.Lock()
        self.max_conversations = max(1, max_conversations)
        self._conversations: "OrderedDict[str, ConversationObject]" = OrderedDict()
        self._items: dict[str, list[ConversationItem]] = {}

    async def create_conversation(
        self, payload: ConversationCreateRequest
    ) -> ConversationObject:
        async with self._lock:
            conversation_id = f"conv_{random_uuid()}"
            now = int(time.time())
            convo = ConversationObject(
                id=conversation_id,
                created_at=now,
                updated_at=now,
                title=payload.title,
                metadata=payload.metadata or {},
                status=payload.status or "active",
            )
            self._evict_if_needed()
            self._conversations[conversation_id] = convo
            self._items[conversation_id] = []
            if payload.items:
                self._items[conversation_id] = self._build_items(payload.items)
                convo.updated_at = int(time.time())
            return convo

    async def update_conversation(
        self, conversation_id: str, payload: ConversationUpdateRequest
    ) -> ConversationObject:
        async with self._lock:
            convo = self._require_conversation(conversation_id)
            if payload.title is not None:
                convo.title = payload.title
            if payload.metadata is not None:
                convo.metadata = payload.metadata
            if payload.status is not None:
                convo.status = payload.status
            convo.updated_at = int(time.time())
            self._conversations.move_to_end(conversation_id)
            return convo

    async def get_conversation(self, conversation_id: str) -> ConversationObject:
        async with self._lock:
            convo = self._require_conversation(conversation_id)
            self._conversations.move_to_end(conversation_id)
            return convo

    async def delete_conversation(self, conversation_id: str) -> bool:
        async with self._lock:
            if conversation_id not in self._conversations:
                return False
            self._conversations.pop(conversation_id, None)
            self._items.pop(conversation_id, None)
            return True

    async def list_items(
        self,
        conversation_id: str,
        *,
        limit: int,
        order: str,
        after: str | None,
    ) -> ConversationListItemsResponse:
        async with self._lock:
            self._require_conversation(conversation_id)
            items = list(self._items.get(conversation_id, []))
            if order == "asc":
                ordered_items = items
            else:
                ordered_items = list(reversed(items))
            start_index = 0
            if after is not None:
                for idx, item in enumerate(ordered_items):
                    if item.id == after:
                        start_index = idx + 1
                        break
                else:
                    raise ConversationNotFoundError(f"Item {after} not found")
            slice_ = ordered_items[start_index : start_index + limit]
            has_more = (start_index + len(slice_)) < len(ordered_items)
            first_id = slice_[0].id if slice_ else None
            last_id = slice_[-1].id if slice_ else None
            return ConversationListItemsResponse(
                data=slice_,
                has_more=has_more,
                first_id=first_id,
                last_id=last_id,
            )

    async def create_items(
        self, conversation_id: str, payload: ConversationItemsCreateRequest
    ) -> list[ConversationItem]:
        async with self._lock:
            convo = self._require_conversation(conversation_id)
            new_items = self._build_items(payload.items)
            self._items.setdefault(conversation_id, []).extend(new_items)
            convo.updated_at = int(time.time())
            return new_items

    async def get_item(
        self, conversation_id: str, item_id: str
    ) -> ConversationItem:
        async with self._lock:
            self._require_conversation(conversation_id)
            for item in self._items.get(conversation_id, []):
                if item.id == item_id:
                    return item
        raise ConversationNotFoundError(item_id)

    async def delete_item(self, conversation_id: str, item_id: str) -> bool:
        async with self._lock:
            self._require_conversation(conversation_id)
            items = self._items.get(conversation_id, [])
            for idx, item in enumerate(items):
                if item.id == item_id:
                    items.pop(idx)
                    return True
        return False

    def _build_items(self, payloads: list[ConversationItemCreate]) -> list[ConversationItem]:
        now = int(time.time())
        created: list[ConversationItem] = []
        for payload in payloads:
            created.append(
                ConversationItem(
                    id=f"item_{random_uuid()}",
                    created_at=now,
                    type=payload.type,
                    role=payload.role,
                    content=payload.content,
                    metadata=payload.metadata,
                )
            )
        return created

    def _require_conversation(self, conversation_id: str) -> ConversationObject:
        convo = self._conversations.get(conversation_id)
        if convo is None:
            raise ConversationNotFoundError(conversation_id)
        return convo

    def _evict_if_needed(self) -> None:
        while len(self._conversations) >= self.max_conversations:
            oldest_id, _ = self._conversations.popitem(last=False)
            self._items.pop(oldest_id, None)
