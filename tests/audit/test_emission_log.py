"""Tests for AuditLog — append-only emission log."""

from __future__ import annotations

import json
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
