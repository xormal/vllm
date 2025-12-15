# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project
"""Compatibility helpers for transformers 4.57.x and 5.x.

This module centralizes best-effort fallbacks so that callers can import a
single place instead of peppering try/except blocks throughout the codebase.
"""

from __future__ import annotations

from typing import Any, Iterable

from packaging.version import Version

from vllm.logger import init_logger

logger = init_logger(__name__)

try:  # COMPAT: transformers v4/v5 version detect
    import transformers

    _TRANSFORMERS_VERSION = Version(getattr(transformers, "__version__", "0.0.0"))
except Exception:  # pragma: no cover
    transformers = None  # type: ignore
    _TRANSFORMERS_VERSION = Version("0.0.0")

TRANSFORMERS_IS_V5 = _TRANSFORMERS_VERSION.major >= 5
if TRANSFORMERS_IS_V5:
    logger.debug("Transformers v5+ detected: %s", _TRANSFORMERS_VERSION)


# ALLOWED_LAYER_TYPES moved in newer transformers; treat as optional.
try:  # transformers <5
    from transformers.configuration_utils import ALLOWED_LAYER_TYPES as _ALT
except Exception:  # pragma: no cover - fallback for transformers>=5
    _ALT = None

ALLOWED_LAYER_TYPES = _ALT

# PretrainedConfig safe import
try:  # transformers <5
    from transformers import PretrainedConfig as _PretrainedConfig  # type: ignore
except Exception:  # pragma: no cover
    _PretrainedConfig = None

PretrainedConfig = _PretrainedConfig


# SAFE_WEIGHTS_INDEX_NAME may move; default to known filename.
try:  # transformers <5
    from transformers.utils import SAFE_WEIGHTS_INDEX_NAME as _SAFE_INDEX
except Exception:  # pragma: no cover
    _SAFE_INDEX = "safe_weights_index.json"

SAFE_WEIGHTS_INDEX_NAME = _SAFE_INDEX


# chat_template_utils may be renamed/removed in transformers 5.
try:  # transformers <5
    import transformers.utils.chat_template_utils as chat_template_utils  # type: ignore
except Exception:  # pragma: no cover
    chat_template_utils = None  # type: ignore


def get_all_special_tokens_extended(tokenizer: Any) -> Iterable[str]:
    """Return extended special tokens with a safe fallback.

    transformers 5 may drop ``all_special_tokens_extended``; fall back to
    ``all_special_tokens`` when unavailable.
    """

    if hasattr(tokenizer, "all_special_tokens_extended"):
        try:
            return tokenizer.all_special_tokens_extended  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover - defensive
            pass
    if hasattr(tokenizer, "all_special_tokens"):
        return tuple(getattr(tokenizer, "all_special_tokens"))
    return ()
