"""Tests for AuditLog — append-only emission log."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from arca_mcp.audit.emission_log import AuditLog


@pytest.fixture
def log_path(tmp_path: Path) -> Path:
    return tmp_path / "audit" / "emission.jsonl"


@pytest.mark.asyncio
async def test_append_writes_valid_json_line(log_path: Path) -> None:
    """A single append produces exactly one valid JSON line."""
    log = AuditLog(log_path)
    entry = {
        "draft_id": "draft-001",
        "cuit": "20123456789",
        "cbte_nro": 1,
        "cae": "12345678901234",
        "idempotency_key": "idem-001",
    }

    await log.append(entry)

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["draft_id"] == "draft-001"
    assert parsed["cae"] == "12345678901234"
    assert "timestamp" in parsed


@pytest.mark.asyncio
async def test_multiple_appends_produce_multiple_lines(log_path: Path) -> None:
    """Each append call produces one additional JSON line."""
    log = AuditLog(log_path)
    entries = [
        {"draft_id": f"draft-{i}", "cuit": "20123456789", "cbte_nro": i, "cae": f"cae-{i}", "idempotency_key": f"idem-{i}"}
        for i in range(5)
    ]

    for entry in entries:
        await log.append(entry)

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 5
    for i, line in enumerate(lines):
        parsed = json.loads(line)
        assert parsed["draft_id"] == f"draft-{i}"
        assert "timestamp" in parsed


def test_no_read_delete_modify_methods_on_audit_log() -> None:
    """AuditLog must not expose any read, delete, or modify public methods."""
    forbidden = {"read", "delete", "remove", "update", "modify", "clear", "reset"}
    public_methods = {
        name
        for name in dir(AuditLog)
        if not name.startswith("_")
    }
    overlap = public_methods & forbidden
    assert not overlap, f"AuditLog exposes forbidden methods: {overlap}"
    assert "append" in public_methods


@pytest.mark.asyncio
async def test_file_permissions_are_0600(log_path: Path) -> None:
    """Audit log file must be readable and writable only by the owner (0600)."""
    log = AuditLog(log_path)
    await log.append({"event": "TEST", "detail": "perms check"})

    assert log_path.exists(), "log file should have been created"
    file_mode = stat.S_IMODE(os.stat(log_path).st_mode)
    assert file_mode == 0o600, f"expected 0600, got {oct(file_mode)}"


@pytest.mark.asyncio
async def test_permissions_enforced_on_pre_existing_file(log_path: Path) -> None:
    """0600 is enforced even when the file already exists with wider permissions."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    # Create file with permissive mode first
    log_path.write_text("", encoding="utf-8")
    os.chmod(log_path, 0o644)

    log = AuditLog(log_path)
    await log.append({"event": "TEST", "detail": "reperms"})

    file_mode = stat.S_IMODE(os.stat(log_path).st_mode)
    assert file_mode == 0o600, f"expected 0600 after append, got {oct(file_mode)}"


@pytest.mark.asyncio
async def test_atomic_write_no_tmp_file_left_on_success(log_path: Path) -> None:
    """After a successful append the .tmp file must not remain."""
    log = AuditLog(log_path)
    await log.append({"event": "TEST", "detail": "atomicity"})

    tmp_path = log_path.with_suffix(log_path.suffix + ".tmp")
    assert not tmp_path.exists(), ".tmp file should be cleaned up after successful write"
    assert log_path.exists(), "real log file should exist"


@pytest.mark.asyncio
async def test_atomic_write_preserves_previous_entries(log_path: Path) -> None:
    """Atomic rename-based append must not lose previously written entries."""
    log = AuditLog(log_path)
    await log.append({"event": "FIRST", "seq": 1})
    await log.append({"event": "SECOND", "seq": 2})
    await log.append({"event": "THIRD", "seq": 3})

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    events = [json.loads(l)["event"] for l in lines]
    assert events == ["FIRST", "SECOND", "THIRD"]


@pytest.mark.asyncio
async def test_pending_cae_entry_survives_simulated_crash(log_path: Path) -> None:
    """PENDING_CAE entry must be durable: simulate a crash after PENDING_CAE is written
    but before CAE_CONFIRMED is written and verify PENDING_CAE is in the log."""
    log = AuditLog(log_path)

    # Write the write-ahead PENDING_CAE entry (as invoicing.py does before WSFE call)
    await log.append(
        {
            "event": "PENDING_CAE",
            "draft_id": "draft-abc",
            "cuit": "20123456789",
            "idempotency_key": "idem-xyz",
            "punto_venta": 1,
            "cbte_tipo": 6,
            "imp_total": "121.00",
        }
    )

    # Simulate crash: do NOT write CAE_CONFIRMED.
    # Verify that PENDING_CAE is still readable from the log.
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["event"] == "PENDING_CAE"
    assert record["draft_id"] == "draft-abc"
    assert record["idempotency_key"] == "idem-xyz"
    assert "timestamp" in record


@pytest.mark.asyncio
async def test_pending_cae_precedes_cae_confirmed(log_path: Path) -> None:
    """In a successful flow, PENDING_CAE must appear before CAE_CONFIRMED in the log."""
    log = AuditLog(log_path)

    await log.append(
        {
            "event": "PENDING_CAE",
            "draft_id": "draft-001",
            "cuit": "20123456789",
            "idempotency_key": "idem-001",
            "punto_venta": 1,
            "cbte_tipo": 6,
            "imp_total": "100.00",
        }
    )
    await log.append(
        {
            "event": "CAE_CONFIRMED",
            "draft_id": "draft-001",
            "cuit": "20123456789",
            "cbte_nro": 42,
            "cae": "99887766554433",
            "idempotency_key": "idem-001",
        }
    )

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    events = [json.loads(l)["event"] for l in lines]
    assert events[0] == "PENDING_CAE"
    assert events[1] == "CAE_CONFIRMED"
