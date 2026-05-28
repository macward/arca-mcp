"""Append-only audit log for voucher emissions."""

from __future__ import annotations

import asyncio
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path


class AuditLog:
    """Append-only emission audit log backed by a JSON-lines file.

    Writes are atomic: each entry is appended to a ``{path}.tmp`` file which
    is then fsync'd and renamed over the real path.  On POSIX systems rename(2)
    is atomic within the same filesystem, so a crash mid-write cannot corrupt
    an existing log.

    The log file is created with permissions 0600 (owner read/write only).

    The only mutation method is ``append``. There are intentionally no read,
    delete, or modify methods — the log is immutable from the application's
    perspective.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._lock = asyncio.Lock()
        self._path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

    async def append(self, entry: dict) -> None:
        """Write *entry* as a single JSON line to the log file.

        A ``timestamp`` field (ISO 8601, UTC) is injected automatically if not
        already present in *entry*.

        The write is atomic: data goes to ``{path}.tmp``, is fsync'd, then
        the tmp file is renamed over the real path so a crash cannot produce a
        partial or corrupt log line.
        """
        record = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            **entry,
        }
        line = json.dumps(record, ensure_ascii=False)

        def _write() -> None:
            tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
            # Read existing content so we can append to it atomically.
            existing = b""
            if self._path.exists():
                existing = self._path.read_bytes()
            new_content = existing + (line + "\n").encode("utf-8")
            # Write to tmp file with 0600 perms, fsync, then rename.
            fd = os.open(
                tmp_path,
                os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                stat.S_IRUSR | stat.S_IWUSR,  # 0600
            )
            try:
                with os.fdopen(fd, "wb") as fh:
                    fh.write(new_content)
                    fh.flush()
                    os.fsync(fh.fileno())
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
            # Atomic rename — replaces real path in one syscall.
            os.replace(tmp_path, self._path)
            # Ensure 0600 on the target (in case it already existed with other perms).
            os.chmod(self._path, stat.S_IRUSR | stat.S_IWUSR)

        async with self._lock:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, _write)
