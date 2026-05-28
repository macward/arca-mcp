"""Crash-recovery tests for IdempotencyStore.cleanup_stale_pending.

Verifies that:
- Stale PENDING entries (older than the threshold) are deleted on startup cleanup.
- Recent PENDING entries (within the threshold) are left untouched.
- DONE entries are never deleted regardless of age.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from arca_mcp.invoicing.idempotency import IdempotencyStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_raw(conn: sqlite3.Connection, key: str, status: str, created_at: str) -> None:
    """Bypass the async API to insert a row with an arbitrary created_at."""
    conn.execute(
        "INSERT INTO entries(key, status, result_json, created_at) VALUES (?, ?, NULL, ?)",
        (key, status, created_at),
    )
    conn.commit()


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _ago(seconds: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(seconds=seconds)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_stale_pending_is_deleted():
    """A PENDING entry older than max_age_seconds must be deleted."""
    store = IdempotencyStore(db_path=":memory:")
    # Insert a PENDING entry that is 10 minutes old (600 s > default 300 s).
    _insert_raw(store._conn, "stale-key", "PENDING", _iso(_ago(600)))

    deleted = store.cleanup_stale_pending(max_age_seconds=300)

    assert deleted == 1
    row = store._conn.execute(
        "SELECT key FROM entries WHERE key='stale-key'"
    ).fetchone()
    assert row is None, "Stale PENDING entry should have been removed"
    store.close()


def test_recent_pending_is_kept():
    """A PENDING entry younger than max_age_seconds must NOT be deleted."""
    store = IdempotencyStore(db_path=":memory:")
    # Insert a PENDING entry that is only 60 s old (< 300 s threshold).
    _insert_raw(store._conn, "recent-key", "PENDING", _iso(_ago(60)))

    deleted = store.cleanup_stale_pending(max_age_seconds=300)

    assert deleted == 0
    row = store._conn.execute(
        "SELECT key FROM entries WHERE key='recent-key'"
    ).fetchone()
    assert row is not None, "Recent PENDING entry should have been preserved"
    store.close()


def test_done_entry_is_never_deleted():
    """DONE entries must survive cleanup regardless of how old they are."""
    store = IdempotencyStore(db_path=":memory:")
    # Very old DONE entry.
    _insert_raw(store._conn, "done-key", "DONE", _iso(_ago(86400)))  # 1 day old

    deleted = store.cleanup_stale_pending(max_age_seconds=300)

    assert deleted == 0
    row = store._conn.execute(
        "SELECT status FROM entries WHERE key='done-key'"
    ).fetchone()
    assert row is not None and row[0] == "DONE", "DONE entry should be untouched"
    store.close()


def test_mixed_entries_only_stale_pending_deleted():
    """Cleanup selectively removes only stale PENDING rows, leaving others intact."""
    store = IdempotencyStore(db_path=":memory:")

    _insert_raw(store._conn, "stale-1", "PENDING", _iso(_ago(600)))
    _insert_raw(store._conn, "stale-2", "PENDING", _iso(_ago(400)))
    _insert_raw(store._conn, "recent", "PENDING", _iso(_ago(60)))
    _insert_raw(store._conn, "done-old", "DONE", _iso(_ago(3600)))

    deleted = store.cleanup_stale_pending(max_age_seconds=300)

    assert deleted == 2

    remaining = {
        row[0]
        for row in store._conn.execute("SELECT key FROM entries").fetchall()
    }
    assert remaining == {"recent", "done-old"}
    store.close()


def test_returns_zero_when_nothing_to_clean():
    """cleanup_stale_pending returns 0 on an empty store."""
    store = IdempotencyStore(db_path=":memory:")
    assert store.cleanup_stale_pending() == 0
    store.close()
