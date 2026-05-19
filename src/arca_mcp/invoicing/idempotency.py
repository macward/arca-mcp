"""In-memory idempotency store for voucher emission."""

from __future__ import annotations

import asyncio


class IdempotencyStore:
    """Thread-safe in-memory store mapping idempotency keys to emission results.

    Intended to prevent double-emission within a single server session.
    For persistence across restarts, pair this with an ``AuditLog``.
    """

    def __init__(self) -> None:
        self._store: dict[str, dict] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> dict | None:
        """Return the result stored under *key*, or ``None`` if not present."""
        async with self._lock:
            return self._store.get(key)

    async def set(self, key: str, result: dict) -> None:
        """Store *result* under *key*."""
        async with self._lock:
            self._store[key] = result
