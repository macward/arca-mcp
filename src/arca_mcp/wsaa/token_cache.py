"""Filesystem cache for WSAA tokens.

One JSON file per CUIT at {cache_dir}/{cuit}.json (default: ~/.arca-mcp/tokens/).
File permissions: 0600. Directory permissions: 0700.
A token is a miss if expired OR if it expires within the refresh threshold (default 10 min).
"""

import datetime
import json
from collections.abc import Callable
from pathlib import Path

from arca_mcp.wsaa.models import WsaaToken

_DEFAULT_CACHE_DIR = Path.home() / ".arca-mcp" / "tokens"
_DEFAULT_REFRESH_THRESHOLD = datetime.timedelta(minutes=10)


class TokenCache:
    def __init__(
        self,
        cache_dir: Path | None = None,
        refresh_threshold_minutes: int = 10,
        _now: Callable[[], datetime.datetime] | None = None,
    ) -> None:
        self._cache_dir = cache_dir or _DEFAULT_CACHE_DIR
        self._refresh_threshold = datetime.timedelta(minutes=refresh_threshold_minutes)
        self._now = _now or (lambda: datetime.datetime.now(datetime.timezone.utc))

    def _path(self, cuit: str) -> Path:
        return self._cache_dir / f"{cuit}.json"

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
        except (KeyError, ValueError, OSError):
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
