"""Append-only audit log for voucher emissions."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path


class AuditLog:
    """Append-only emission audit log backed by a JSON-lines file.

    The only mutation method is ``append``. There are intentionally no read,
    delete, or modify methods — the log is immutable from the application's
    perspective.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._lock = asyncio.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    async def append(self, entry: dict) -> None:
        """Write *entry* as a single JSON line to the log file.

        A ``timestamp`` field (ISO 8601, UTC) is injected automatically if not
        already present in *entry*.
        """
        record = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            **entry,
        }
        line = json.dumps(record, ensure_ascii=False)

        def _write() -> None:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")

        async with self._lock:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, _write)
