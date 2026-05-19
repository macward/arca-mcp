"""Filesystem cache for WSAA tokens.

One JSON file per CUIT at {cache_dir}/{cuit}.json (default: ~/.arca-mcp/tokens/).
Override the default with the ARCA_TOKEN_CACHE_DIR environment variable.
File permissions: 0600. Directory permissions: 0700.
A token is a miss if expired OR if it expires within the refresh threshold (default 10 min).

Concurrency: get_or_refresh() uses one asyncio.Lock per CUIT (check-lock-check pattern)
so that only one coroutine performs the login when multiple hit a cache miss simultaneously.
The blocking refresh_fn is offloaded to a thread pool to avoid stalling the event loop.
"""

import asyncio
import datetime
import json
import logging
import os
from collections.abc import Callable
from pathlib import Path

from pydantic import ValidationError

from arca_mcp.wsaa.models import WsaaToken

logger = logging.getLogger(__name__)

_DEFAULT_CACHE_DIR = Path.home() / ".arca-mcp" / "tokens"
_ENV_VAR = "ARCA_TOKEN_CACHE_DIR"


def _resolve_cache_dir(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit
    env = os.environ.get(_ENV_VAR)
    if env:
        return Path(env)
    return _DEFAULT_CACHE_DIR


class TokenCache:
    def __init__(
        self,
        cache_dir: Path | None = None,
        refresh_threshold_minutes: int = 10,
        _now: Callable[[], datetime.datetime] | None = None,
    ) -> None:
        self._cache_dir = _resolve_cache_dir(cache_dir)
        self._refresh_threshold = datetime.timedelta(minutes=refresh_threshold_minutes)
        self._now = _now or (lambda: datetime.datetime.now(datetime.timezone.utc))
        self._locks: dict[str, asyncio.Lock] = {}
        self._ensure_cache_dir()

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

    def _path(self, cuit: str) -> Path:
        return self._cache_dir / f"{cuit}.json"

    def _get_lock(self, cuit: str) -> asyncio.Lock:
        if cuit not in self._locks:
            self._locks[cuit] = asyncio.Lock()
        return self._locks[cuit]

    def _parse_expiry(self, raw: str) -> datetime.datetime:
        dt = datetime.datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt

    def is_near_expiry(self, token: WsaaToken) -> bool:
        """Return True if the token expires within the refresh threshold."""
        try:
            expiration_time = self._parse_expiry(token.expiration_time)
        except ValueError:
            return True
        return expiration_time - self._now() < self._refresh_threshold

    def get(self, cuit: str) -> WsaaToken | None:
        """Return WsaaToken if a valid non-expired, non-near-expiry token exists.

        Returns None if the file doesn't exist, expiration_time <= now, or the
        token is within the refresh threshold (triggering proactive refresh).
        """
        path = self._path(cuit)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            expiration_time = self._parse_expiry(data.get("expiration_time", ""))
            now = self._now()
            if expiration_time <= now:
                path.unlink(missing_ok=True)
                return None
            token = WsaaToken(**data)
            if self.is_near_expiry(token):
                return None
            return token
        except (ValueError, OSError, ValidationError) as e:
            logger.warning("TokenCache: token ignorado para cuit=%s: %s", cuit, e)
            return None

    def save(self, cuit: str, token: WsaaToken) -> None:
        """Persist token to disk with 0600 permissions."""
        self._cache_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = self._path(cuit)
        path.write_text(token.model_dump_json())
        path.chmod(0o600)

    def invalidate(self, cuit: str) -> None:
        """Remove cached token for the given CUIT."""
        self._path(cuit).unlink(missing_ok=True)

    async def get_or_refresh(
        self,
        cuit: str,
        refresh_fn: Callable[[], WsaaToken],
    ) -> WsaaToken:
        """Return a valid token, refreshing via refresh_fn if needed.

        Uses check-lock-check pattern: only one coroutine per CUIT performs
        the login when multiple hit a cache miss simultaneously.
        refresh_fn is executed in a thread pool to avoid blocking the event loop.
        """
        token = self.get(cuit)
        if token is not None:
            return token

        async with self._get_lock(cuit):
            token = self.get(cuit)
            if token is not None:
                return token
            loop = asyncio.get_running_loop()
            token = await loop.run_in_executor(None, refresh_fn)
            self.save(cuit, token)
            return token
