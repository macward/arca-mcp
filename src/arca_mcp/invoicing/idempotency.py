"""SQLite-backed idempotency store for voucher emission.

Entries survive process crashes so that a key claimed right before a WSFE
SOAP call is still visible after a restart, preventing double-emission.

Schema
------
entries(key TEXT PRIMARY KEY, status TEXT, result_json TEXT, created_at TEXT)

Status values
-------------
PENDING  Claimed before the WSFE call; result_json is NULL.
DONE     Settled after the WSFE call; result_json holds the JSON payload.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    key         TEXT PRIMARY KEY,
    status      TEXT NOT NULL,
    result_json TEXT,
    created_at  TEXT NOT NULL
);
"""


class IdempotencyStore:
    """Thread-safe SQLite-backed store mapping idempotency keys to emission results.

    Parameters
    ----------
    db_path:
        Path to the SQLite database file.  Use ``":memory:"`` for an
        in-process, non-persistent store (handy in tests).  Defaults to
        ``~/.arca-mcp/idempotency.db``.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            db_path = Path.home() / ".arca-mcp" / "idempotency.db"
        self._db_path = str(db_path)
        if self._db_path != ":memory:":
            Path(self._db_path).parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(
            self._db_path,
            check_same_thread=False,
        )
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Primary interface (task spec)
    # ------------------------------------------------------------------

    async def set_pending(self, key: str) -> bool:
        """Atomically claim *key* with status PENDING.

        Returns True if the key was newly inserted, False if it already
        existed (concurrent or retried call).
        """
        with self._lock:
            try:
                self._conn.execute(
                    "INSERT INTO entries(key, status, result_json, created_at) "
                    "VALUES (?, 'PENDING', NULL, ?)",
                    (key, _now()),
                )
                self._conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    async def set_done(self, key: str, result: dict[str, Any]) -> None:
        """Update *key* to DONE and persist *result* as JSON."""
        with self._lock:
            self._conn.execute(
                "UPDATE entries SET status='DONE', result_json=? WHERE key=?",
                (json.dumps(result), key),
            )
            self._conn.commit()

    async def get(self, key: str) -> tuple[str, dict | None] | None:
        """Return ``(status, result)`` for *key*, or ``None`` if not found.

        *result* is ``None`` when status is PENDING.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT status, result_json FROM entries WHERE key=?",
                (key,),
            ).fetchone()
        if row is None:
            return None
        status, result_json = row
        result = json.loads(result_json) if result_json is not None else None
        return status, result

    # ------------------------------------------------------------------
    # Lifecycle helpers
    # ------------------------------------------------------------------

    async def delete(self, key: str) -> None:
        """Remove *key* from the store (no-op if not present).

        Used on error paths so the caller can retry with the same key.
        """
        with self._lock:
            self._conn.execute("DELETE FROM entries WHERE key=?", (key,))
            self._conn.commit()

    def cleanup_stale_pending(self, max_age_seconds: int = 300) -> int:
        """Delete PENDING entries older than *max_age_seconds*.

        Called at startup to reclaim keys whose owning process crashed between
        ``set_pending`` and ``set_done``.  Entries younger than the threshold
        are left untouched because they may belong to an in-flight operation
        in another process.

        Parameters
        ----------
        max_age_seconds:
            Age in seconds past which a PENDING entry is considered stale.
            Default is 300 (5 minutes).

        Returns
        -------
        int
            Number of rows deleted.
        """
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)
        cutoff_iso = cutoff.isoformat()
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM entries WHERE status='PENDING' AND created_at < ?",
                (cutoff_iso,),
            )
            self._conn.commit()
            return cursor.rowcount

    def close(self) -> None:
        """Close the underlying database connection."""
        with self._lock:
            self._conn.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
