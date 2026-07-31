"""Tests de validación de fechas de calendario para modelos wsfe e invoicing."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from arca_mcp.invoicing.models import DraftStatus, VoucherDraft
from arca_mcp.wsfe.models import (
    FECAESolicitarRequest,
    FECAESolicitarResponse,
    FECompConsultarResponse,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now():
    return datetime.now(timezone.utc)


def _make_draft(**overrides: Any) -> VoucherDraft:
    defaults: dict[str, Any] = dict(
        draft_id=str(uuid.uuid4()),
        status=DraftStatus.PENDING,
        cbte_tipo=1,
        punto_venta=1,
        fecha_cbte="20260519",
        cuit_receptor="20123456789",
        doc_tipo=80,
        imp_neto=Decimal("1000.00"),
        alicuota_id="5",
        created_at=_now(),
        updated_at=_now(),
    )
    defaults.update(overrides)
    return VoucherDraft(**defaults)


def _make_request(**overrides: Any) -> FECAESolicitarRequest:
    defaults: dict[str, Any] = dict(
        cuit="20123456789",
        punto_venta=1,
        cbte_tipo=1,
        fecha_cbte="20260519",
        cuit_receptor="20123456789",
        doc_tipo=80,
        imp_neto=Decimal("1000.00"),
        imp_iva=Decimal("210.00"),
        imp_total=Decimal("1210.00"),
        alicuota_id="5",
    )
    defaults.update(overrides)
    return FECAESolicitarRequest(**defaults)


def _make_cae_response(**overrides: Any) -> FECAESolicitarResponse:
    defaults: dict[str, Any] = dict(
        cae="12345678901234",
        cbte_nro=1,
        cae_fch_vto="20260529",
        resultado="A",
        observaciones=[],
    )
    defaults.update(overrides)
    return FECAESolicitarResponse(**defaults)


def _make_consultar_response(**overrides: Any) -> FECompConsultarResponse:
    defaults: dict[str, Any] = dict(
        cbte_nro=1,
        cbte_tipo=1,
        punto_venta=1,
        cae="12345678901234",
        cae_fch_vto="20260529",
        fecha_cbte="20260519",
        resultado="A",
        doc_tipo=80,
        doc_nro="20123456789",
        imp_total=Decimal("1210.00"),
        imp_neto=Decimal("1000.00"),
        imp_iva=Decimal("210.00"),
    )
    defaults.update(overrides)
    return FECompConsultarResponse(**defaults)


# ---------------------------------------------------------------------------
# VoucherDraft.fecha_cbte
# ---------------------------------------------------------------------------

class TestVoucherDraftFechaCbte:
    def test_valid_date_accepted(self):
        draft = _make_draft(fecha_cbte="20260519")
        assert draft.fecha_cbte == "20260519"

    def test_invalid_calendar_date_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            _make_draft(fecha_cbte="20260230")
        assert "fecha_cbte" in str(exc_info.value)

    def test_invalid_month_rejected(self):
        with pytest.raises(ValidationError):
            _make_draft(fecha_cbte="20261301")

    def test_end_of_month_valid(self):
        draft = _make_draft(fecha_cbte="20260131")
        assert draft.fecha_cbte == "20260131"

    def test_leap_year_valid(self):
        draft = _make_draft(fecha_cbte="20240229")
        assert draft.fecha_cbte == "20240229"

    def test_non_leap_year_feb29_rejected(self):
        with pytest.raises(ValidationError):
            _make_draft(fecha_cbte="20250229")


# ---------------------------------------------------------------------------
# FECAESolicitarRequest.fecha_cbte
# ---------------------------------------------------------------------------

class TestFECAESolicitarRequestFechaCbte:
    def test_valid_date_accepted(self):
        req = _make_request(fecha_cbte="20260519")
        assert req.fecha_cbte == "20260519"

    def test_invalid_calendar_date_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            _make_request(fecha_cbte="20260230")
        assert "fecha_cbte" in str(exc_info.value)


# ---------------------------------------------------------------------------
# FECAESolicitarResponse.cae_fch_vto
# ---------------------------------------------------------------------------

class TestFECAESolicitarResponseCaeFchVto:
    def test_valid_date_accepted(self):
        resp = _make_cae_response(cae_fch_vto="20260529")
        assert resp.cae_fch_vto == "20260529"

    def test_invalid_calendar_date_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            _make_cae_response(cae_fch_vto="20260230")
        assert "cae_fch_vto" in str(exc_info.value)


# ---------------------------------------------------------------------------
# FECompConsultarResponse — both fields
# ---------------------------------------------------------------------------

class TestFECompConsultarResponseDates:
    def test_valid_dates_accepted(self):
        resp = _make_consultar_response()
        assert resp.fecha_cbte == "20260519"
        assert resp.cae_fch_vto == "20260529"

    def test_invalid_fecha_cbte_rejected(self):
        with pytest.raises(ValidationError):
            _make_consultar_response(fecha_cbte="20260230")

    def test_invalid_cae_fch_vto_rejected(self):
        with pytest.raises(ValidationError):
            _make_consultar_response(cae_fch_vto="20260230")
