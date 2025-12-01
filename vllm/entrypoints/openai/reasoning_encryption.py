# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project

"""Utility helper for encrypting reasoning content in the Responses API."""

from __future__ import annotations

import base64
import os
from typing import Any

from vllm.logger import init_logger

logger = init_logger(__name__)

try:
    from cryptography.fernet import Fernet

    _HAS_FERNET = True
except Exception:  # pragma: no cover - optional dependency
    Fernet = None
    _HAS_FERNET = False


class ReasoningEncryption:
    """Encrypt/decrypt reasoning payloads for response.additional_context."""

    def __init__(self, encryption_key: str | None = None) -> None:
        self._encryption_key = encryption_key or self._generate_ephemeral_key()
        self._cipher = self._build_cipher(self._encryption_key)

    @staticmethod
    def _generate_ephemeral_key() -> str:
        """Generate an ephemeral key for development usage."""

        random_bytes = os.urandom(32)
        key = base64.urlsafe_b64encode(random_bytes).decode("ascii")
        logger.warning(
            "No reasoning encryption key provided; generated ephemeral key. "
            "Provide --reasoning-encryption-key for consistent encrypted output."
        )
        return key

    def _build_cipher(self, key: str) -> Any | None:
        """Return a Fernet cipher if cryptography is available."""

        if not _HAS_FERNET:
            logger.warning_once(
                "cryptography is not installed; reasoning content will be "
                "Base64-encoded but not encrypted."
            )
            return None

        try:
            return Fernet(key.encode("utf-8"))
        except Exception as exc:  # pragma: no cover - initialization failure
            logger.warning(
                "Failed to initialize Fernet cipher (%s); "
                "falling back to Base64-only encoding.",
                exc,
            )
            return None

    def encrypt_reasoning(self, reasoning_text: str) -> str:
        """Encrypt reasoning text (Base64 if encryption unavailable)."""

        data = reasoning_text.encode("utf-8")
        if self._cipher is not None:
            token = self._cipher.encrypt(data)
            return token.decode("utf-8")
        return base64.b64encode(data).decode("ascii")

    def decrypt_reasoning(self, encrypted_payload: str) -> str:
        """Decrypt reasoning text (Base64 decode when cipher unavailable)."""

        data = encrypted_payload.encode("utf-8")
        if self._cipher is not None:
            plaintext = self._cipher.decrypt(data)
            return plaintext.decode("utf-8")
        decoded = base64.b64decode(data)
        return decoded.decode("utf-8")

    @property
    def encryption_key(self) -> str:
        return self._encryption_key
