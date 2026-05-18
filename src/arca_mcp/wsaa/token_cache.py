"""Filesystem cache for WSAA tokens.

One JSON file per CUIT at {cache_dir}/{cuit}.json (default: ~/.arca-mcp/tokens/).
File permissions: 0600. Directory permissions: 0700.
A token is a miss if expiration_time <= utcnow().
"""

import datetime
import json
from pathlib import Path

from arca_mcp.wsaa.models import WsaaToken

_DEFAULT_CACHE_DIR = Path.home() / ".arca-mcp" / "tokens"


class TokenCache:
    def __init__(self, cache_dir: Path | None = None) -> None:
        self._cache_dir = cache_dir or _DEFAULT_CACHE_DIR

    def _path(self, cuit: str) -> Path:
        return self._cache_dir / f"{cuit}.json"

    def get(self, cuit: str) -> WsaaToken | None:
        """Return WsaaToken if a valid non-expired token exists, else None."""
        path = self._path(cuit)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            raw_exp = data.get("expiration_time", "")
            expiration_time = datetime.datetime.fromisoformat(raw_exp)
            if expiration_time.tzinfo is None:
                expiration_time = expiration_time.replace(tzinfo=datetime.timezone.utc)
            if expiration_time <= datetime.datetime.now(datetime.timezone.utc):
                path.unlink(missing_ok=True)
                return None
            return WsaaToken(**data)
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
