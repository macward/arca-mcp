"""Unified WSAA token cache: in-memory (threading.Lock) + filesystem (asyncio.Lock per CUIT).

Replaces the former two-layer design (token_store + TokenCache) with a single class.

In-memory layer
---------------
- Key: (cuit, service)
- Protected by a single threading.Lock (safe for both sync and asyncio-executor threads)
- TTL: tokens within 10 minutes of expiry are treated as expired

Filesystem layer
----------------
- One JSON file per CUIT at {cache_dir}/{cuit}.json  (default: ~/.arca-mcp/tokens/)
- Per-CUIT asyncio.Lock (check-lock-check) prevents duplicate logins under concurrent requests
- Files are written atomically with 0600 permissions
- Configurable via ARCA_TOKEN_CACHE_DIR environment variable
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
import threading
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

from pydantic import ValidationError

from arca_mcp.wsaa.models import WsaaToken

logger = logging.getLogger(__name__)

_DEFAULT_CACHE_DIR = Path.home() / ".arca-mcp" / "tokens"
_ENV_VAR = "ARCA_TOKEN_CACHE_DIR"
_VALIDITY_BUFFER = datetime.timedelta(minutes=10)


def _resolve_cache_dir(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit
    env = os.environ.get(_ENV_VAR)
    if env:
        return Path(env)
    return _DEFAULT_CACHE_DIR


def _to_aware_utc(value: datetime.datetime | str) -> datetime.datetime:
    if isinstance(value, str):
        value = datetime.datetime.fromisoformat(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=datetime.timezone.utc)
    return value.astimezone(datetime.timezone.utc)


class WsaaCache:
    """Unified WSAA token cache with in-memory and filesystem layers.

    In-memory lookup is O(1) with a threading.Lock — safe for both asyncio
    and executor threads.  Filesystem persistence uses one asyncio.Lock per
    CUIT so that concurrent async callers never trigger duplicate logins.

    Parameters
    ----------
    cache_dir:
        Override the directory used for filesystem token files.
        Falls back to ARCA_TOKEN_CACHE_DIR env var, then ~/.arca-mcp/tokens/.
    refresh_threshold_minutes:
        Tokens expiring within this window are treated as expired (proactive refresh).
    _now:
        Injectable clock for testing.
    """

    def __init__(
        self,
        cache_dir: Path | None = None,
        refresh_threshold_minutes: int = 10,
        _now: Callable[[], datetime.datetime] | None = None,
    ) -> None:
        self._cache_dir = _resolve_cache_dir(cache_dir)
        self._refresh_threshold = datetime.timedelta(minutes=refresh_threshold_minutes)
        self._now = _now or (lambda: datetime.datetime.now(datetime.timezone.utc))

        # In-memory layer
        self._mem: dict[tuple[str, str], tuple[str, str, datetime.datetime]] = {}
        self._mem_lock = threading.Lock()

        # Filesystem layer — per-CUIT asyncio locks
        self._fs_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

        self._ensure_cache_dir()

    # ------------------------------------------------------------------
    # In-memory layer
    # ------------------------------------------------------------------

    def get(self, cuit: str, service: str = "_default") -> WsaaToken | None:
        """Return a valid in-memory token or None.

        Only checks the in-memory layer. Expired / near-expiry entries are evicted on access.
        For a full check that includes the filesystem layer, use get_or_refresh().
        The legacy single-argument form (cuit only) also checks the filesystem for backward
        compatibility with code that previously used TokenCache.get(cuit).
        """
        key = (cuit, service)
        with self._mem_lock:
            entry = self._mem.get(key)
            if entry is not None:
                token, sign, expiration_time = entry
                now = self._now()
                if expiration_time > now + _VALIDITY_BUFFER:
                    return WsaaToken(
                        token=token,
                        sign=sign,
                        generation_time="cached",
                        expiration_time=expiration_time.isoformat(),
                    )
                del self._mem[key]
                return None

        # Legacy single-arg compat: if service was not specified, also check filesystem
        if service == "_default":
            return self._fs_get(cuit)
        return None

    def set(self, cuit: str, service: str, token: WsaaToken) -> None:
        """Write a token to the in-memory layer."""
        key = (cuit, service)
        exp = _to_aware_utc(token.expiration_time)
        with self._mem_lock:
            self._mem[key] = (token.token, token.sign, exp)

    def invalidate(self, cuit: str, service: str | None = None) -> None:
        """Remove in-memory entries for the given CUIT (and optionally service).

        If service is None, all in-memory entries for that CUIT are removed.
        Always also removes the filesystem token for the CUIT.
        """
        with self._mem_lock:
            if service is not None:
                self._mem.pop((cuit, service), None)
            else:
                keys = [k for k in self._mem if k[0] == cuit]
                for k in keys:
                    del self._mem[k]
        # Also evict from disk
        self._fs_path(cuit).unlink(missing_ok=True)

    def clear(self) -> None:
        """Remove all in-memory entries (does not touch filesystem)."""
        with self._mem_lock:
            self._mem.clear()

    # ------------------------------------------------------------------
    # Filesystem layer
    # ------------------------------------------------------------------

    def _ensure_cache_dir(self) -> None:
        try:
            self._cache_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        except OSError as e:
            raise ValueError(
                f"No se puede crear el directorio de caché de tokens "
                f"'{self._cache_dir}': {e}"
            ) from e
        if not os.access(self._cache_dir, os.W_OK):
            raise ValueError(
                f"El directorio de caché de tokens '{self._cache_dir}' no es escribible. "
                f"Verificá permisos o configurá {_ENV_VAR} con un path alternativo."
            )

    def _fs_path(self, cuit: str) -> Path:
        return self._cache_dir / f"{cuit}.json"

    def _fs_get(self, cuit: str) -> WsaaToken | None:
        """Read token from disk. Returns None on miss, expiry, or near-expiry."""
        path = self._fs_path(cuit)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            raw_exp = data.get("expiration_time", "")
            exp = _to_aware_utc(raw_exp) if raw_exp else None
            if exp is None:
                return None
            now = self._now()
            if exp <= now:
                path.unlink(missing_ok=True)
                return None
            token = WsaaToken(**data)
            if exp - now < self._refresh_threshold:
                return None
            return token
        except (ValueError, OSError, ValidationError) as e:
            logger.warning("WsaaCache: token ignorado para cuit=%s: %s", cuit, e)
            return None

    def _fs_save(self, cuit: str, token: WsaaToken) -> None:
        """Persist token to disk with 0600 permissions (atomic write)."""
        self._cache_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = self._fs_path(cuit)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(token.model_dump_json())
        os.chmod(tmp, 0o600)
        tmp.replace(path)

    def save(self, cuit: str, token: WsaaToken) -> None:
        """Persist token to disk (public alias for _fs_save)."""
        self._fs_save(cuit, token)

    def _get_fs_lock(self, cuit: str) -> asyncio.Lock:
        return self._fs_locks[cuit]

    # Backward-compat alias used by tests
    def _get_lock(self, cuit: str) -> asyncio.Lock:
        return self._get_fs_lock(cuit)

    def _path(self, cuit: str) -> Path:
        """Backward-compat alias for _fs_path."""
        return self._fs_path(cuit)

    def is_near_expiry(self, token: WsaaToken) -> bool:
        """Return True if the token expires within the refresh threshold."""
        try:
            exp = _to_aware_utc(token.expiration_time)
        except ValueError:
            return True
        return exp - self._now() < self._refresh_threshold

    async def get_or_refresh(
        self,
        cuit: str,
        service: str | Callable[[], WsaaToken],
        refresh_fn: Callable[[], WsaaToken] | None = None,
    ) -> WsaaToken:
        """Return a valid token, refreshing via refresh_fn if needed.

        Supports two call signatures for backward compatibility:
          - get_or_refresh(cuit, service, refresh_fn)   [preferred]
          - get_or_refresh(cuit, refresh_fn)             [legacy, service defaults to "_default"]
        """
        # Handle legacy 2-arg form: get_or_refresh(cuit, refresh_fn)
        _service: str
        if callable(service) and refresh_fn is None:
            refresh_fn = service
            _service = "_default"
        elif isinstance(service, str):
            _service = service
        else:
            raise TypeError("service must be a str or a callable refresh_fn")
        if refresh_fn is None:
            raise TypeError("refresh_fn is required")

        # Check order: in-memory → filesystem → network (check-lock-check per CUIT)
        # Fast path: in-memory
        token = self.get(cuit, _service)
        if token is not None:
            return token

        async with self._get_fs_lock(cuit):
            # Re-check in-memory under lock (another coroutine may have refreshed)
            token = self.get(cuit, _service)
            if token is not None:
                return token

            # Check filesystem
            token = self._fs_get(cuit)
            if token is not None:
                self.set(cuit, _service, token)
                return token

            # Network login
            loop = asyncio.get_running_loop()
            token = await loop.run_in_executor(None, refresh_fn)
            self._fs_save(cuit, token)
            self.set(cuit, _service, token)
            return token
