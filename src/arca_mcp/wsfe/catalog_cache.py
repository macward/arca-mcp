"""In-memory TTL cache for WSFEv1 catalog responses.

Catalogs (voucher types, aliquots, currencies, etc.) change at most a few times
per year. Caching them avoids redundant SOAP round-trips and keeps the server
functional when ARCA is degraded.

Cache is process-scoped and not persisted — a fresh fetch happens on restart.
"""

import time
from collections.abc import Callable
from typing import Any

TTL_SECONDS: int = 86400  # 24 hours

_store: dict[str, tuple[Any, float]] = {}


def _key(fn: Callable, environment: str) -> str:
    name = getattr(fn, "__name__", None) or repr(fn)
    return f"{name}:{environment}"


def get(fn: Callable, environment: str) -> Any | None:
    """Return cached data for (fn, environment), or None if missing/expired."""
    entry = _store.get(_key(fn, environment))
    if entry is None:
        return None
    data, ts = entry
    if time.monotonic() - ts > TTL_SECONDS:
        _store.pop(_key(fn, environment), None)
        return None
    return data


def set(fn: Callable, environment: str, data: Any) -> None:
    """Store data for (fn, environment) with the current timestamp."""
    _store[_key(fn, environment)] = (data, time.monotonic())


def clear() -> None:
    """Evict all entries. Useful in tests."""
    _store.clear()
