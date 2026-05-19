"""Unit tests for DraftStore and VoucherDraft."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from arca_mcp.invoicing.draft_store import (
    DraftNotFoundError,
    DraftStore,
    InvalidStatusTransitionError,
)
from arca_mcp.invoicing.models import DraftStatus, VoucherDraft


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_draft(**overrides) -> VoucherDraft:
    """Return a minimal valid VoucherDraft, with optional field overrides."""
    now = datetime.now(timezone.utc)
    defaults = dict(
        draft_id=str(uuid.uuid4()),
        status=DraftStatus.PENDING,
        cbte_tipo=1,
        punto_venta=1,
        fecha_cbte="20260519",
        cuit_receptor="20123456789",
        doc_tipo=80,
        imp_neto=Decimal("1000.00"),
        alicuota_id="5",  # 21 %
        created_at=now,
        updated_at=now,
    )
    defaults.update(overrides)
    return VoucherDraft(**defaults)


# ---------------------------------------------------------------------------
# VoucherDraft model tests
# ---------------------------------------------------------------------------


class TestVoucherDraftModel:
    def test_computed_imp_iva_21_percent(self):
        draft = make_draft(imp_neto=Decimal("1000.00"), alicuota_id="5")
        assert draft.imp_iva == Decimal("210.00")

    def test_computed_imp_iva_10_5_percent(self):
        draft = make_draft(imp_neto=Decimal("1000.00"), alicuota_id="4")
        assert draft.imp_iva == Decimal("105.00")

    def test_computed_imp_iva_zero_percent(self):
        draft = make_draft(imp_neto=Decimal("1000.00"), alicuota_id="3")
        assert draft.imp_iva == Decimal("0.00")

    def test_computed_imp_total(self):
        draft = make_draft(imp_neto=Decimal("1000.00"), alicuota_id="5")
        assert draft.imp_total == Decimal("1210.00")

    def test_invalid_alicuota_raises(self):
        with pytest.raises(ValueError, match="alicuota_id"):
            make_draft(alicuota_id="99")

    def test_invalid_cuit_format_raises(self):
        with pytest.raises(ValueError):
            make_draft(cuit_receptor="123")  # too short

    def test_invalid_fecha_cbte_format_raises(self):
        with pytest.raises(ValueError):
            make_draft(fecha_cbte="2026/05/19")  # wrong format


# ---------------------------------------------------------------------------
# DraftStore tests
# ---------------------------------------------------------------------------


class TestDraftStoreCreate:
    @pytest.mark.asyncio
    async def test_create_and_retrieve(self):
        store = DraftStore()
        draft = make_draft()
        created = await store.create(draft)
        assert created.draft_id == draft.draft_id
        retrieved = await store.get(draft.draft_id)
        assert retrieved is not None
        assert retrieved.draft_id == draft.draft_id

    @pytest.mark.asyncio
    async def test_create_duplicate_raises(self):
        store = DraftStore()
        draft = make_draft()
        await store.create(draft)
        with pytest.raises(ValueError, match="already exists"):
            await store.create(draft)

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self):
        store = DraftStore()
        result = await store.get("nonexistent-id")
        assert result is None


class TestDraftStoreUpdateStatus:
    @pytest.mark.asyncio
    async def test_pending_to_validated(self):
        store = DraftStore()
        draft = make_draft()
        await store.create(draft)
        updated = await store.update_status(draft.draft_id, DraftStatus.VALIDATED)
        assert updated.status == DraftStatus.VALIDATED

    @pytest.mark.asyncio
    async def test_pending_to_rejected(self):
        store = DraftStore()
        draft = make_draft()
        await store.create(draft)
        updated = await store.update_status(draft.draft_id, DraftStatus.REJECTED)
        assert updated.status == DraftStatus.REJECTED

    @pytest.mark.asyncio
    async def test_validated_to_confirmed(self):
        store = DraftStore()
        draft = make_draft()
        await store.create(draft)
        await store.update_status(draft.draft_id, DraftStatus.VALIDATED)
        updated = await store.update_status(draft.draft_id, DraftStatus.CONFIRMED)
        assert updated.status == DraftStatus.CONFIRMED

    @pytest.mark.asyncio
    async def test_confirmed_is_terminal(self):
        store = DraftStore()
        draft = make_draft()
        await store.create(draft)
        await store.update_status(draft.draft_id, DraftStatus.VALIDATED)
        await store.update_status(draft.draft_id, DraftStatus.CONFIRMED)
        with pytest.raises(InvalidStatusTransitionError):
            await store.update_status(draft.draft_id, DraftStatus.REJECTED)

    @pytest.mark.asyncio
    async def test_rejected_is_terminal(self):
        store = DraftStore()
        draft = make_draft()
        await store.create(draft)
        await store.update_status(draft.draft_id, DraftStatus.REJECTED)
        with pytest.raises(InvalidStatusTransitionError):
            await store.update_status(draft.draft_id, DraftStatus.VALIDATED)

    @pytest.mark.asyncio
    async def test_invalid_transition_pending_to_confirmed(self):
        store = DraftStore()
        draft = make_draft()
        await store.create(draft)
        with pytest.raises(InvalidStatusTransitionError) as exc_info:
            await store.update_status(draft.draft_id, DraftStatus.CONFIRMED)
        assert exc_info.value.current == DraftStatus.PENDING
        assert exc_info.value.requested == DraftStatus.CONFIRMED

    @pytest.mark.asyncio
    async def test_update_nonexistent_raises(self):
        store = DraftStore()
        with pytest.raises(DraftNotFoundError):
            await store.update_status("ghost-id", DraftStatus.VALIDATED)

    @pytest.mark.asyncio
    async def test_update_sets_updated_at(self):
        store = DraftStore()
        draft = make_draft()
        await store.create(draft)
        original_updated_at = draft.updated_at
        updated = await store.update_status(draft.draft_id, DraftStatus.VALIDATED)
        assert updated.updated_at >= original_updated_at

    @pytest.mark.asyncio
    async def test_updated_draft_is_persisted(self):
        """After update_status, get() returns the new status."""
        store = DraftStore()
        draft = make_draft()
        await store.create(draft)
        await store.update_status(draft.draft_id, DraftStatus.VALIDATED)
        retrieved = await store.get(draft.draft_id)
        assert retrieved is not None
        assert retrieved.status == DraftStatus.VALIDATED


class TestDraftStoreIsolation:
    @pytest.mark.asyncio
    async def test_multiple_drafts_independent(self):
        store = DraftStore()
        draft_a = make_draft()
        draft_b = make_draft()
        await store.create(draft_a)
        await store.create(draft_b)
        await store.update_status(draft_a.draft_id, DraftStatus.VALIDATED)
        b = await store.get(draft_b.draft_id)
        assert b is not None
        assert b.status == DraftStatus.PENDING  # draft_b is unaffected

    @pytest.mark.asyncio
    async def test_clear_empties_store(self):
        store = DraftStore()
        await store.create(make_draft())
        await store.create(make_draft())
        assert len(store) == 2
        await store.clear()
        assert len(store) == 0
