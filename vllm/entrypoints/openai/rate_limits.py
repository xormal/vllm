# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project

"""Simple rate limit tracker for emitting rate_limits.updated events."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Deque

from vllm.entrypoints.openai.protocol import RateLimitInfo
from vllm.logger import init_logger

logger = init_logger(__name__)


@dataclass
class RateLimitConfig:
    enabled: bool = False
    enforce: bool = True
    request_limits_enabled: bool = True
    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    token_limits_enabled: bool = True
    tokens_per_minute: int = 100_000

    @classmethod
    def from_dict(cls, data: dict | None) -> "RateLimitConfig":
        if not data:
            return cls()
        request_limits = data.get("request_limits", {})
        token_limits = data.get("token_limits", {})
        return cls(
            enabled=bool(data.get("enabled", True)),
            enforce=bool(data.get("enforce", True)),
            request_limits_enabled=bool(request_limits.get("enabled", True)),
            requests_per_minute=int(request_limits.get("per_minute", 60)),
            requests_per_hour=int(request_limits.get("per_hour", 1000)),
            token_limits_enabled=bool(token_limits.get("enabled", True)),
            tokens_per_minute=int(token_limits.get("per_minute", 100_000)),
        )


@dataclass
class RateLimitWindow:
    window_seconds: int
    max_count: int
    entries: Deque[tuple[float, int]] = field(default_factory=deque)

    def add(self, count: int = 1, *, now: float | None = None) -> None:
        if count <= 0:
            return
        now = time.time() if now is None else now
        self.entries.append((now, count))
        self._prune(now)

    def _prune(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self.entries and self.entries[0][0] < cutoff:
            self.entries.popleft()

    def usage_percent(self, *, now: float | None = None) -> float:
        now = time.time() if now is None else now
        self._prune(now)
        total = sum(entry[1] for entry in self.entries)
        if self.max_count <= 0:
            return 0.0
        return min(100.0, (total / self.max_count) * 100.0)

    def total(self, *, now: float | None = None) -> int:
        now = time.time() if now is None else now
        self._prune(now)
        return sum(entry[1] for entry in self.entries)


class RateLimitTracker:
    """Tracks request/token counts for emitting rate limit events."""

    def __init__(
        self,
        *,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000,
        tokens_per_minute: int = 100_000,
        enable_request_limits: bool = True,
        enable_token_limits: bool = True,
    ) -> None:
        self._requests_per_minute = max(requests_per_minute, 1)
        self._requests_per_hour = max(requests_per_hour, 1)
        self._tokens_per_minute = max(tokens_per_minute, 1)
        self._enable_request_limits = enable_request_limits
        self._enable_token_limits = enable_token_limits
        self._lock = asyncio.Lock()
        self._windows: dict[str, dict[str, RateLimitWindow]] = defaultdict(dict)

    async def record_request(self, user_id: str) -> None:
        if not self._enable_request_limits:
            return
        async with self._lock:
            windows = self._ensure_user_windows(user_id)
            now = time.time()
            windows["requests_1min"].add(1, now=now)
            windows["requests_1hour"].add(1, now=now)

    async def record_tokens(self, user_id: str, token_count: int) -> None:
        if token_count <= 0 or not self._enable_token_limits:
            return
        async with self._lock:
            windows = self._ensure_user_windows(user_id)
            windows["tokens_1min"].add(token_count)

    async def check_and_reserve(
        self,
        user_id: str,
        *,
        tokens: int = 0,
    ) -> tuple[bool, float | None]:
        async with self._lock:
            windows = self._ensure_user_windows(user_id)
            now = time.time()
            wait_times: list[float] = []
            if self._enable_request_limits:
                wait_times.extend(
                    filter(
                        lambda t: t > 0,
                        [
                            self._wait_time_until_available(
                                windows["requests_1min"], 1, now
                            ),
                            self._wait_time_until_available(
                                windows["requests_1hour"], 1, now
                            ),
                        ],
                    )
                )
            if self._enable_token_limits and tokens > 0:
                wait = self._wait_time_until_available(
                    windows["tokens_1min"], tokens, now
                )
                if wait > 0:
                    wait_times.append(wait)
            if wait_times:
                return False, max(wait_times)
            if self._enable_request_limits:
                windows["requests_1min"].add(1, now=now)
                windows["requests_1hour"].add(1, now=now)
            if self._enable_token_limits and tokens > 0:
                windows["tokens_1min"].add(tokens, now=now)
            return True, None

    async def build_rate_limit_payload(
        self, user_id: str
    ) -> dict[str, RateLimitInfo]:
        async with self._lock:
            windows = self._ensure_user_windows(user_id)
            now = time.time()
            return {
                "primary": RateLimitInfo(
                    used_percent=windows["requests_1min"].usage_percent(now=now),
                    window_minutes=1,
                    limit_type="primary",
                ),
                "requests": RateLimitInfo(
                    used_percent=windows["requests_1hour"].usage_percent(now=now),
                    window_minutes=60,
                    limit_type="requests",
                ),
                "tokens": RateLimitInfo(
                    used_percent=windows["tokens_1min"].usage_percent(now=now),
                    window_minutes=1,
                    limit_type="tokens",
                ),
            }

    async def build_header_stats(
        self, user_id: str
    ) -> dict[str, dict[str, int]]:
        async with self._lock:
            windows = self._ensure_user_windows(user_id)
            now = time.time()
            stats: dict[str, dict[str, int]] = {}
            for name, window in windows.items():
                limit = window.max_count
                remaining = max(0, limit - window.total(now=now))
                stats[name] = {"limit": limit, "remaining": remaining}
            return stats

    def _ensure_user_windows(self, user_id: str) -> dict[str, RateLimitWindow]:
        windows = self._windows[user_id]
        if not windows:
            windows["requests_1min"] = RateLimitWindow(
                60, self._requests_per_minute
            )
            windows["requests_1hour"] = RateLimitWindow(
                60 * 60, self._requests_per_hour
            )
            windows["tokens_1min"] = RateLimitWindow(
                60, self._tokens_per_minute
            )
        return windows

    @staticmethod
    def _wait_time_until_available(
        window: RateLimitWindow, amount: int, now: float
    ) -> float:
        window._prune(now)
        current_total = sum(count for _, count in window.entries)
        if current_total + amount <= window.max_count:
            return 0.0
        running = current_total
        for timestamp, count in list(window.entries):
            running -= count
            if running + amount <= window.max_count:
                return max(0.0, timestamp + window.window_seconds - now)
        # Fallback: wait entire window
        if window.entries:
            oldest_timestamp = window.entries[0][0]
            return max(0.0, oldest_timestamp + window.window_seconds - now)
        return window.window_seconds
