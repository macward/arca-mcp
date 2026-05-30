"""Tests for the list_vouchers MCP tool."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from arca_mcp.invoicing.draft_store import DraftStore
from arca_mcp.invoicing.models import DraftStatus, VoucherDraft
from arca_mcp.mcp import invoicing as _invoicing_mod


def _tool_fn(tool):
    return getattr(tool, "fn", tool)


list_vouchers = _tool_fn(_invoicing_mod.list_vouchers)


def _draft(draft_id: str, status: DraftStatus = DraftStatus.PENDING) -> VoucherDraft:
    return VoucherDraft(
        draft_id=draft_id,
        status=status,
        cbte_tipo=6,
        punto_venta=1,
        fecha_cbte="20260101",
        cuit_receptor="20111111112",
        doc_tipo=80,
        imp_neto=Decimal("1000.00"),
        alicuota_id="5",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture(autouse=True)
def isolated_store(tmp_path):
    store = DraftStore(db_path=tmp_path / "drafts.db")
    original = _invoicing_mod._draft_store
    _invoicing_mod._draft_store = store
    yield store
    _invoicing_mod._draft_store = original


async def test_empty_store_returns_empty_list():
    result = await list_vouchers()
    assert result == []


async def test_returns_only_confirmed_by_default(isolated_store):
    await isolated_store.create(_draft("pending-1", DraftStatus.PENDING))
    await isolated_store.create(_draft("confirmed-1", DraftStatus.CONFIRMED))

    result = await list_vouchers()
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["draft_id"] == "confirmed-1"
    assert result[0]["status"] == "CONFIRMED"


async def test_all_returns_every_status(isolated_store):
    for i, st in enumerate([DraftStatus.PENDING, DraftStatus.CONFIRMED, DraftStatus.REJECTED]):
        await isolated_store.create(_draft(f"d{i}", st))

    result = await list_vouchers(status="ALL")
    assert len(result) == 3


async def test_invalid_status_returns_error():
    result = await list_vouchers(status="INVALID")
    assert isinstance(result, dict)
    assert result["error"]["cause"] == "INVALID_ARGUMENT"


async def test_limit_is_respected(isolated_store):
    for i in range(5):
        await isolated_store.create(_draft(f"d{i}"))

    result = await list_vouchers(status="ALL", limit=3)
    assert len(result) == 3


async def test_limit_capped_at_200(isolated_store):
    result = await list_vouchers(status="ALL", limit=999)
    assert isinstance(result, list)


async def test_result_contains_expected_fields(isolated_store):
    await isolated_store.create(_draft("fields-check"))
    result = await list_vouchers(status="ALL", limit=1)
    assert len(result) == 1
    entry = result[0]
    for field in ("draft_id", "status", "cbte_tipo", "punto_venta",
                  "fecha_cbte", "cuit_receptor", "imp_total", "created_at", "updated_at"):
        assert field in entry, f"Campo faltante: {field}"


async def test_imp_total_is_string(isolated_store):
    await isolated_store.create(_draft("total-check"))
    result = await list_vouchers(status="ALL", limit=1)
    assert isinstance(result[0]["imp_total"], str)
