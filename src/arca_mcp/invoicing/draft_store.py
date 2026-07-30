"""SQLite-backed store for VoucherDraft instances.

Drafts survive process crashes so that PENDING or VALIDATED drafts are
recoverable after a restart.  The in-process interface is unchanged —
all methods are async and raise the same exceptions as before.

Schema
------
drafts(draft_id TEXT PRIMARY KEY, status TEXT, data_json TEXT,
       created_at TEXT, updated_at TEXT)

data_json holds ``VoucherDraft.model_dump_json()``; status is denormalized
for cheap list_pending queries without deserializing every row.

Only homologación drafts are supported at this stage.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from arca_mcp.invoicing.models import DraftStatus, VoucherDraft

_SCHEMA = """
CREATE TABLE IF NOT EXISTS drafts (
    draft_id   TEXT PRIMARY KEY,
    status     TEXT NOT NULL,
    data_json  TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


class DraftNotFoundError(Exception):
    """Raised when a draft_id does not exist in the store."""

    def __init__(self, draft_id: str) -> None:
        super().__init__(f"Draft not found: {draft_id}")
        self.draft_id = draft_id


class InvalidStatusTransitionError(Exception):
    """Raised when a requested status transition is not allowed."""

    def __init__(
        self, draft_id: str, current: DraftStatus, requested: DraftStatus
    ) -> None:
        super().__init__(
            f"Cannot transition draft {draft_id} from {current} to {requested}."
        )
        self.draft_id = draft_id
        self.current = current
        self.requested = requested


# Allowed forward transitions.
_ALLOWED_TRANSITIONS: dict[DraftStatus, set[DraftStatus]] = {
    DraftStatus.PENDING: {DraftStatus.VALIDATED, DraftStatus.REJECTED},
    DraftStatus.VALIDATED: {DraftStatus.CONFIRMED, DraftStatus.REJECTED},
    DraftStatus.CONFIRMED: set(),
    DraftStatus.REJECTED: set(),
}


class DraftStore:
    """SQLite-backed, thread-safe store for VoucherDraft objects.

    Parameters
    ----------
    db_path:
        Path to the SQLite database file.  Use ``":memory:"`` for an
        in-process, non-persistent store (handy in tests).  Defaults to
        ``~/.arca-mcp/drafts.db``.

    Usage::

        store = DraftStore()
        draft = await store.create(my_draft)
        retrieved = await store.get(draft.draft_id)
        updated = await store.update_status(draft.draft_id, DraftStatus.VALIDATED)
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            db_path = Path.home() / ".arca-mcp" / "drafts.db"
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

    async def create(self, draft: VoucherDraft) -> VoucherDraft:
        """Persist a new draft in the store and return it.

        Raises:
            ValueError: if a draft with the same draft_id already exists.
        """
        with self._lock:
            existing = self._conn.execute(
                "SELECT 1 FROM drafts WHERE draft_id=?", (draft.draft_id,)
            ).fetchone()
            if existing is not None:
                raise ValueError(
                    f"Draft with id '{draft.draft_id}' already exists."
                )
            self._conn.execute(
                "INSERT INTO drafts(draft_id, status, data_json, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    draft.draft_id,
                    draft.status.value,
                    draft.model_dump_json(),
                    draft.created_at.isoformat(),
                    draft.updated_at.isoformat(),
                ),
            )
            self._conn.commit()
        return draft

    async def get(self, draft_id: str) -> VoucherDraft | None:
        """Return the draft for *draft_id*, or None if not found."""
        with self._lock:
            row = self._conn.execute(
                "SELECT data_json FROM drafts WHERE draft_id=?", (draft_id,)
            ).fetchone()
        if row is None:
            return None
        return VoucherDraft.model_validate_json(row[0])

    async def update_status(
        self, draft_id: str, new_status: DraftStatus
    ) -> VoucherDraft:
        """Transition *draft_id* to *new_status* and return the updated draft.

        Raises:
            DraftNotFoundError: if the draft does not exist.
            InvalidStatusTransitionError: if the transition is not allowed.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT data_json FROM drafts WHERE draft_id=?", (draft_id,)
            ).fetchone()
            if row is None:
                raise DraftNotFoundError(draft_id)

            draft = VoucherDraft.model_validate_json(row[0])

            allowed = _ALLOWED_TRANSITIONS[draft.status]
            if new_status not in allowed:
                raise InvalidStatusTransitionError(draft_id, draft.status, new_status)

            updated = draft.model_copy(
                update={
                    "status": new_status,
                    "updated_at": datetime.now(timezone.utc),
                }
            )
            self._conn.execute(
                "UPDATE drafts SET status=?, data_json=?, updated_at=? WHERE draft_id=?",
                (
                    updated.status.value,
                    updated.model_dump_json(),
                    updated.updated_at.isoformat(),
                    draft_id,
                ),
            )
            self._conn.commit()
        return updated

    async def list_pending(self) -> list[VoucherDraft]:
        """Return all drafts currently in PENDING or VALIDATED state."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT data_json FROM drafts WHERE status IN ('PENDING', 'VALIDATED')"
            ).fetchall()
        return [VoucherDraft.model_validate_json(row[0]) for row in rows]

    async def list_by_status(
        self,
        statuses: list[str] | None = None,
        limit: int = 50,
    ) -> list[VoucherDraft]:
        """Return drafts filtered by status, ordered by created_at DESC.

        Parameters
        ----------
        statuses:
            List of DraftStatus values to include. None means all statuses.
        limit:
            Maximum number of results to return.
        """
        with self._lock:
            if statuses:
                placeholders = ",".join("?" * len(statuses))
                rows = self._conn.execute(
                    f"SELECT data_json FROM drafts WHERE status IN ({placeholders}) "
                    f"ORDER BY created_at DESC LIMIT ?",
                    (*statuses, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT data_json FROM drafts ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [VoucherDraft.model_validate_json(row[0]) for row in rows]

    async def clear(self) -> None:
        """Remove all drafts from the store (useful for tests)."""
        with self._lock:
            self._conn.execute("DELETE FROM drafts")
            self._conn.commit()

    def __len__(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) FROM drafts").fetchone()
        return row[0] if row else 0

    def close(self) -> None:
        """Close the underlying database connection."""
        with self._lock:
            self._conn.close()
