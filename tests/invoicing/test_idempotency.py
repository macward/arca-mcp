"""Tests for the IdempotencyStore primary interface (anti double-emission).

Covers the claim lifecycle that guarantees a voucher is never emitted twice:
- Claiming a fresh key succeeds.
- Re-claiming a key already in flight (PENDING) or settled (DONE) is rejected.
- Settling a claim stores the result so retries replay it instead of re-emitting.
- Releasing a claim on an error path frees the key for a legitimate retry.

Crash recovery (``cleanup_stale_pending``) lives in
``test_idempotency_crash_recovery.py``.
"""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path

from arca_mcp.invoicing.idempotency import IdempotencyStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _store() -> IdempotencyStore:
    return IdempotencyStore(db_path=":memory:")


_RESULT = {"cae": "71234567890123", "numero": 42, "vencimiento_cae": "20260810"}


# ---------------------------------------------------------------------------
# set_pending — claiming a key
# ---------------------------------------------------------------------------


async def test_set_pending_claims_a_fresh_key():
    """A key never seen before is claimed and left in PENDING with no result."""
    store = _store()

    assert await store.set_pending("key-nueva") is True
    assert await store.get("key-nueva") == ("PENDING", None)

    store.close()


async def test_set_pending_rejects_a_key_already_claimed():
    """Re-claiming an in-flight key returns False — this is the anti-double-emission gate."""
    store = _store()
    assert await store.set_pending("key-repetida") is True

    assert await store.set_pending("key-repetida") is False
    # The original claim is untouched by the rejected attempt.
    assert await store.get("key-repetida") == ("PENDING", None)

    store.close()


async def test_set_pending_rejects_a_key_already_settled():
    """A DONE key cannot be re-claimed: the emission already happened."""
    store = _store()
    await store.set_pending("key-emitida")
    await store.set_done("key-emitida", _RESULT)

    assert await store.set_pending("key-emitida") is False
    assert await store.get("key-emitida") == ("DONE", _RESULT)

    store.close()


async def test_set_pending_claims_are_independent_per_key():
    """Claiming one key does not block a different key."""
    store = _store()

    assert await store.set_pending("key-a") is True
    assert await store.set_pending("key-b") is True

    store.close()


def test_set_pending_is_thread_safe_only_one_claim_wins():
    """Under concurrent claims for the same key, exactly one caller wins."""
    store = _store()
    barrier = threading.Barrier(8)
    results: list[bool] = []
    results_lock = threading.Lock()

    def claim() -> None:
        barrier.wait()
        won = asyncio.run(store.set_pending("key-carrera"))
        with results_lock:
            results.append(won)

    threads = [threading.Thread(target=claim) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(results) == 8, "Every thread must have reported a verdict"
    assert results.count(True) == 1, "Exactly one concurrent claim must succeed"
    assert results.count(False) == 7

    store.close()


# ---------------------------------------------------------------------------
# set_done — settling a claim
# ---------------------------------------------------------------------------


async def test_set_done_stores_the_result_for_replay():
    """Settling a claim flips it to DONE and persists the payload verbatim."""
    store = _store()
    await store.set_pending("key-cae")

    await store.set_done("key-cae", _RESULT)

    assert await store.get("key-cae") == ("DONE", _RESULT)

    store.close()


async def test_set_done_on_unknown_key_creates_nothing():
    """Settling a key that was never claimed is a no-op (UPDATE matches no row)."""
    store = _store()

    await store.set_done("key-fantasma", _RESULT)

    assert await store.get("key-fantasma") is None

    store.close()


# ---------------------------------------------------------------------------
# get — inspecting a key
# ---------------------------------------------------------------------------


async def test_get_returns_none_for_unknown_key():
    """An unclaimed key reports None so the caller knows it may proceed."""
    store = _store()

    assert await store.get("key-inexistente") is None

    store.close()


async def test_get_roundtrips_nested_result_payloads():
    """The stored result survives the JSON roundtrip, nesting included."""
    store = _store()
    payload = {"cae": "7100", "observaciones": [{"code": 10, "msg": "ok"}], "neto": "121.00"}
    await store.set_pending("key-anidada")

    await store.set_done("key-anidada", payload)

    assert await store.get("key-anidada") == ("DONE", payload)

    store.close()


# ---------------------------------------------------------------------------
# delete — releasing a claim on an error path
# ---------------------------------------------------------------------------


async def test_delete_releases_the_claim_so_the_key_can_be_retried():
    """After an error the claim is released and the same key can be claimed again."""
    store = _store()
    await store.set_pending("key-fallida")

    await store.delete("key-fallida")

    assert await store.get("key-fallida") is None
    assert await store.set_pending("key-fallida") is True

    store.close()


async def test_delete_is_a_noop_for_unknown_key():
    """Deleting a key that was never claimed does not raise."""
    store = _store()

    await store.delete("key-inexistente")

    assert await store.get("key-inexistente") is None

    store.close()


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_default_db_path_lives_under_home_with_private_permissions(tmp_path, monkeypatch):
    """Without an explicit path the store lands in ~/.arca-mcp/ with a 0700 parent."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    store = IdempotencyStore()

    db_path = tmp_path / ".arca-mcp" / "idempotency.db"
    assert db_path.exists()
    assert db_path.parent.stat().st_mode & 0o777 == 0o700

    store.close()


def test_entries_persist_across_store_instances(tmp_path):
    """A claim written by one process is visible to the next one (crash safety)."""
    db_path = tmp_path / "idempotency.db"
    first = IdempotencyStore(db_path=db_path)
    asyncio.run(first.set_pending("key-persistida"))
    asyncio.run(first.set_done("key-persistida", _RESULT))
    first.close()

    second = IdempotencyStore(db_path=db_path)
    assert asyncio.run(second.get("key-persistida")) == ("DONE", _RESULT)
    second.close()
