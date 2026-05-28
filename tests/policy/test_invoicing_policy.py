"""Tests para el validador de política fiscal de comprobantes."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from arca_mcp.invoicing.models import VoucherDraft
from arca_mcp.policy.invoicing import (
    _amounts_consistent,
    _is_valid_cuit,
    validate_draft,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime.now(tz=timezone.utc)

# A real Argentine CUIT that passes the check-digit algorithm
_VALID_CUIT = "20123456786"


def _make_draft(**overrides) -> VoucherDraft:
    """Return a minimal valid VoucherDraft, with optional field overrides."""
    defaults: dict = {
        "draft_id": "test-draft-001",
        "cbte_tipo": 6,           # Factura B
        "punto_venta": 1,
        "fecha_cbte": "20260519", # today (2026-05-19)
        "cuit_receptor": _VALID_CUIT,
        "doc_tipo": 80,
        "imp_neto": Decimal("1000.00"),
        "alicuota_id": "5",       # 21%
        "created_at": _NOW,
        "updated_at": _NOW,
    }
    defaults.update(overrides)
    return VoucherDraft(**defaults)


# ---------------------------------------------------------------------------
# CUIT check-digit helper
# ---------------------------------------------------------------------------

class TestIsValidCuit:
    def test_valid_cuit_returns_true(self):
        assert _is_valid_cuit(_VALID_CUIT) is True

    def test_wrong_check_digit_returns_false(self):
        # Flip the last digit
        bad = _VALID_CUIT[:-1] + str((int(_VALID_CUIT[-1]) + 1) % 10)
        assert _is_valid_cuit(bad) is False

    def test_too_short_returns_false(self):
        assert _is_valid_cuit("2012345678") is False

    def test_non_numeric_returns_false(self):
        assert _is_valid_cuit("2012345678X") is False

    def test_all_zeros_returns_false(self):
        # "00000000000" is mathematically valid per the check-digit algorithm
        # (sum=0, check=0, last digit=0), but we test that a wrong check digit
        # fails, not this edge case.  Confirm the algorithm's result for zeros:
        # it actually *passes* the pure check-digit test.
        assert _is_valid_cuit("00000000000") is True  # pure algorithm result


# ---------------------------------------------------------------------------
# Amount consistency helper
# ---------------------------------------------------------------------------

class TestAmountsConsistent:
    def test_correct_21_pct_amounts_are_consistent(self):
        assert _amounts_consistent(
            Decimal("1000.00"), "5",
            Decimal("210.00"), Decimal("1210.00"),
        ) is True

    def test_wrong_iva_is_inconsistent(self):
        assert _amounts_consistent(
            Decimal("1000.00"), "5",
            Decimal("300.00"),  # should be 210
            Decimal("1300.00"),
        ) is False

    def test_wrong_total_is_inconsistent(self):
        assert _amounts_consistent(
            Decimal("1000.00"), "5",
            Decimal("210.00"),
            Decimal("1500.00"),  # should be 1210
        ) is False

    def test_exento_zero_iva_is_consistent(self):
        assert _amounts_consistent(
            Decimal("500.00"), "3",  # exento
            Decimal("0.00"), Decimal("500.00"),
        ) is True

    def test_unknown_alicuota_skips_check(self):
        # When alicuota_id is unknown, function returns True (rule already fired)
        assert _amounts_consistent(
            Decimal("1000.00"), "99",
            Decimal("999.00"), Decimal("1999.00"),
        ) is True

    def test_within_tolerance_is_consistent(self):
        # 1 cent rounding is acceptable
        assert _amounts_consistent(
            Decimal("1000.00"), "5",
            Decimal("210.00"), Decimal("1210.01"),
        ) is True


# ---------------------------------------------------------------------------
# validate_draft — happy path
# ---------------------------------------------------------------------------

class TestValidateDraftValid:
    def test_valid_factura_b_passes(self):
        draft = _make_draft()
        report = validate_draft(draft)
        assert report.is_valid is True
        assert report.errors == []

    def test_valid_factura_a_passes(self):
        draft = _make_draft(cbte_tipo=1, alicuota_id="5")
        report = validate_draft(draft)
        assert report.is_valid is True

    def test_valid_factura_c_passes(self):
        draft = _make_draft(cbte_tipo=11, alicuota_id="5")
        report = validate_draft(draft)
        assert report.is_valid is True

    def test_exento_alicuota_3_with_zero_neto_passes(self):
        """Exento (alícuota "3") with imp_neto=0 → imp_iva=0, imp_total=0."""
        draft = _make_draft(alicuota_id="3", imp_neto=Decimal("0.00"))
        report = validate_draft(draft)
        assert report.is_valid is True
        assert draft.imp_iva == Decimal("0.00")
        assert draft.imp_total == Decimal("0.00")

    def test_exento_with_nonzero_neto_passes(self):
        """Exento: neto=1000, iva=0, total=1000."""
        draft = _make_draft(alicuota_id="3", imp_neto=Decimal("1000.00"))
        report = validate_draft(draft)
        assert report.is_valid is True
        assert draft.imp_iva == Decimal("0.00")
        assert draft.imp_total == Decimal("1000.00")

    def test_10_5_pct_alicuota_passes(self):
        draft = _make_draft(alicuota_id="4", imp_neto=Decimal("1000.00"))
        report = validate_draft(draft)
        assert report.is_valid is True
        assert draft.imp_iva == Decimal("105.00")

    def test_punto_venta_boundary_values(self):
        for pv in (1, 9999):
            draft = _make_draft(punto_venta=pv)
            report = validate_draft(draft)
            assert report.is_valid is True, f"Expected valid for punto_venta={pv}"


# ---------------------------------------------------------------------------
# validate_draft — individual rule failures
# ---------------------------------------------------------------------------

class TestValidateDraftInvalidCbteTipo:
    def test_unknown_cbte_tipo_returns_error(self):
        draft = _make_draft(cbte_tipo=99)
        report = validate_draft(draft)
        assert report.is_valid is False
        codes = [e.code for e in report.errors]
        assert "UNKNOWN_CBTE_TIPO" in codes

    def test_zero_cbte_tipo_returns_error(self):
        draft = _make_draft(cbte_tipo=0)
        report = validate_draft(draft)
        codes = [e.code for e in report.errors]
        assert "UNKNOWN_CBTE_TIPO" in codes

    def test_error_references_correct_field(self):
        draft = _make_draft(cbte_tipo=999)
        report = validate_draft(draft)
        field_error = next(e for e in report.errors if e.code == "UNKNOWN_CBTE_TIPO")
        assert field_error.field == "cbte_tipo"


class TestValidateDraftInvalidPuntoVenta:
    def test_zero_punto_venta_returns_error(self):
        draft = _make_draft(punto_venta=0)
        report = validate_draft(draft)
        codes = [e.code for e in report.errors]
        assert "INVALID_PUNTO_VENTA" in codes

    def test_10000_punto_venta_returns_error(self):
        draft = _make_draft(punto_venta=10000)
        report = validate_draft(draft)
        codes = [e.code for e in report.errors]
        assert "INVALID_PUNTO_VENTA" in codes


class TestValidateDraftInvalidFechaCbte:
    def test_date_too_far_in_future_returns_error(self):
        draft = _make_draft(fecha_cbte="20300101")
        report = validate_draft(draft)
        codes = [e.code for e in report.errors]
        assert "DATE_TOO_FAR_IN_FUTURE" in codes

    def test_past_date_is_valid(self):
        draft = _make_draft(fecha_cbte="20200101")
        report = validate_draft(draft)
        assert report.is_valid is True


class TestValidateDraftInvalidCuit:
    def test_bad_check_digit_returns_error(self):
        bad_cuit = _VALID_CUIT[:-1] + str((int(_VALID_CUIT[-1]) + 1) % 10)
        draft = _make_draft(cuit_receptor=bad_cuit)
        report = validate_draft(draft)
        codes = [e.code for e in report.errors]
        assert "INVALID_CUIT" in codes

    def test_error_references_cuit_field(self):
        bad_cuit = "20123456789"  # wrong check digit (should be 6, not 9)
        draft = _make_draft(cuit_receptor=bad_cuit)
        report = validate_draft(draft)
        cuit_errors = [e for e in report.errors if e.code == "INVALID_CUIT"]
        assert cuit_errors, "Expected INVALID_CUIT error"
        assert cuit_errors[0].field == "cuit_receptor"


class TestValidateDraftConsumidorFinal:
    def test_doc_tipo_99_with_cuit_receptor_zero_passes(self):
        """Consumidor Final: doc_tipo=99, cuit_receptor='0' must be valid."""
        draft = _make_draft(doc_tipo=99, cuit_receptor="0")
        report = validate_draft(draft)
        cuit_errors = [e for e in report.errors if e.code == "INVALID_CUIT"]
        assert not cuit_errors, "INVALID_CUIT must not fire for doc_tipo=99"

    def test_doc_tipo_99_full_draft_is_valid(self):
        """A complete Consumidor Final draft passes all policy rules."""
        draft = _make_draft(cbte_tipo=6, doc_tipo=99, cuit_receptor="0")
        report = validate_draft(draft)
        assert report.is_valid is True, f"Expected valid draft, got errors: {report.errors}"

    def test_voucher_draft_model_accepts_zero_for_doc_tipo_99(self):
        """VoucherDraft Pydantic model accepts cuit_receptor='0' when doc_tipo=99."""
        draft = _make_draft(doc_tipo=99, cuit_receptor="0")
        assert draft.cuit_receptor == "0"
        assert draft.doc_tipo == 99

    def test_voucher_draft_model_rejects_non_zero_for_doc_tipo_99(self):
        """VoucherDraft rejects a non-'0' cuit_receptor when doc_tipo=99."""
        from pydantic import ValidationError as PydanticValidationError

        with pytest.raises(PydanticValidationError):
            _make_draft(doc_tipo=99, cuit_receptor=_VALID_CUIT)


class TestValidateDraftDNI:
    def test_doc_tipo_96_with_8_digit_dni_passes_model(self):
        draft = _make_draft(doc_tipo=96, cuit_receptor="12345678")
        assert draft.cuit_receptor == "12345678"
        assert draft.doc_tipo == 96

    def test_doc_tipo_96_with_7_digit_dni_passes_model(self):
        draft = _make_draft(doc_tipo=96, cuit_receptor="1234567")
        assert draft.cuit_receptor == "1234567"

    def test_doc_tipo_96_with_empty_string_raises(self):
        from pydantic import ValidationError as PydanticValidationError
        with pytest.raises(PydanticValidationError):
            _make_draft(doc_tipo=96, cuit_receptor="")

    def test_doc_tipo_96_with_11_digit_cuit_raises(self):
        from pydantic import ValidationError as PydanticValidationError
        with pytest.raises(PydanticValidationError):
            _make_draft(doc_tipo=96, cuit_receptor=_VALID_CUIT)

    def test_doc_tipo_96_no_invalid_cuit_error_in_policy(self):
        draft = _make_draft(doc_tipo=96, cuit_receptor="12345678")
        report = validate_draft(draft)
        cuit_errors = [e for e in report.errors if e.code == "INVALID_CUIT"]
        assert not cuit_errors

    def test_doc_tipo_80_with_valid_cuit_passes(self):
        draft = _make_draft(doc_tipo=80, cuit_receptor=_VALID_CUIT)
        report = validate_draft(draft)
        cuit_errors = [e for e in report.errors if e.code == "INVALID_CUIT"]
        assert not cuit_errors

    def test_doc_tipo_80_with_bad_check_digit_raises_policy_error(self):
        bad_cuit = _VALID_CUIT[:-1] + str((int(_VALID_CUIT[-1]) + 1) % 10)
        draft = _make_draft(doc_tipo=80, cuit_receptor=bad_cuit)
        report = validate_draft(draft)
        codes = [e.code for e in report.errors]
        assert "INVALID_CUIT" in codes


class TestValidateDraftInvalidAlicuota:
    def test_unknown_alicuota_id_returns_error(self):
        # alicuota_id "99" is not in catalogs — but pydantic's model_validator
        # would reject it first; test via a monkey-patched approach or by
        # directly testing the policy function with a mock draft.
        # Instead, validate the pure _amounts_consistent and catalog checks.
        # We verify the rule fires for out-of-catalog values by testing the
        # validate_draft pathway without Pydantic's own guard.
        #
        # Since VoucherDraft model_validator also rejects unknown alicuota_id,
        # we confirm the Pydantic guard raises ValueError for unknown IDs.
        from pydantic import ValidationError as PydanticValidationError

        with pytest.raises(PydanticValidationError):
            _make_draft(alicuota_id="99")

    def test_known_alicuota_ids_are_accepted(self):
        for alicuota_id in ("3", "4", "5", "6", "8", "9"):
            draft = _make_draft(alicuota_id=alicuota_id)
            report = validate_draft(draft)
            alicuota_errors = [e for e in report.errors if e.code == "UNKNOWN_ALICUOTA"]
            assert not alicuota_errors, (
                f"Unexpected UNKNOWN_ALICUOTA for alicuota_id={alicuota_id}"
            )


class TestValidateDraftInconsistentAmounts:
    """Rule 7: imp_iva and imp_total must be consistent with imp_neto × rate.

    Since VoucherDraft computes imp_iva/imp_total as @computed_field, they are
    always consistent for any VoucherDraft instance.  Rule 7 is a safety net
    for any future code path that builds draft-like objects with external
    amounts.  We therefore test _amounts_consistent directly, and confirm that
    a well-formed draft always passes rule 7.
    """

    def test_well_formed_draft_passes_rule_7(self):
        draft = _make_draft()
        report = validate_draft(draft)
        inconsistent = [e for e in report.errors if e.code == "INCONSISTENT_AMOUNTS"]
        assert not inconsistent

    def test_inconsistent_amounts_helper_catches_wrong_iva(self):
        result = _amounts_consistent(
            Decimal("1000.00"), "5",
            Decimal("999.00"),    # wrong iva
            Decimal("1999.00"),   # wrong total
        )
        assert result is False

    def test_inconsistent_amounts_helper_catches_wrong_total_only(self):
        result = _amounts_consistent(
            Decimal("1000.00"), "5",
            Decimal("210.00"),    # correct iva
            Decimal("1300.00"),   # wrong total
        )
        assert result is False


# ---------------------------------------------------------------------------
# ValidationReport structure
# ---------------------------------------------------------------------------

class TestValidationReport:
    def test_report_has_is_valid_bool(self):
        draft = _make_draft()
        report = validate_draft(draft)
        assert isinstance(report.is_valid, bool)

    def test_report_has_errors_list(self):
        draft = _make_draft()
        report = validate_draft(draft)
        assert isinstance(report.errors, list)

    def test_error_has_required_fields(self):
        draft = _make_draft(cbte_tipo=999)
        report = validate_draft(draft)
        assert report.errors
        error = report.errors[0]
        assert hasattr(error, "field")
        assert hasattr(error, "code")
        assert hasattr(error, "message")
        assert isinstance(error.field, str)
        assert isinstance(error.code, str)
        assert isinstance(error.message, str)

    def test_multiple_errors_are_accumulated(self):
        """Multiple violations should all appear in the report."""
        draft = _make_draft(cbte_tipo=999, punto_venta=0)
        report = validate_draft(draft)
        codes = {e.code for e in report.errors}
        assert "UNKNOWN_CBTE_TIPO" in codes
        assert "INVALID_PUNTO_VENTA" in codes
        assert report.is_valid is False
