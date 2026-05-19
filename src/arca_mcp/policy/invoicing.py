"""Fiscal policy validator for VoucherDraft.

All functions are pure: no side effects, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal

from arca_mcp.invoicing.models import VoucherDraft
from arca_mcp.validation.catalogs import IVA_ALIQUOTS, INVOICE_TYPES


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidationError:
    """A single policy violation detected in a VoucherDraft."""

    field: str
    code: str
    message: str


@dataclass
class ValidationReport:
    """Aggregate result of validate_draft()."""

    is_valid: bool
    errors: list[ValidationError] = field(default_factory=list)


# ---------------------------------------------------------------------------
# CUIT check-digit validation
# ---------------------------------------------------------------------------

_CUIT_WEIGHTS = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)


def _is_valid_cuit(cuit: str) -> bool:
    """Return True if *cuit* passes the Argentine CUIT check-digit algorithm."""
    if len(cuit) != 11 or not cuit.isdigit():
        return False
    digits = [int(d) for d in cuit]
    total = sum(w * d for w, d in zip(_CUIT_WEIGHTS, digits[:10]))
    remainder = total % 11
    check = 0 if remainder == 0 else (11 - remainder)
    # check == 10 is formally invalid per AFIP spec
    if check == 10:
        return False
    return check == digits[10]


# ---------------------------------------------------------------------------
# Date validation
# ---------------------------------------------------------------------------

_MAX_FUTURE_DAYS = 5


def _parse_fecha_cbte(fecha: str) -> date | None:
    """Parse YYYYMMDD string to date; return None on failure."""
    try:
        return datetime.strptime(fecha, "%Y%m%d").date()
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Amount tolerance
# ---------------------------------------------------------------------------

# Allow 1 cent rounding tolerance when comparing computed vs declared amounts.
_AMOUNT_TOLERANCE = Decimal("0.01")


def _amounts_consistent(
    imp_neto: Decimal,
    alicuota_id: str,
    imp_iva: Decimal,
    imp_total: Decimal,
) -> bool:
    """Return True if imp_iva and imp_total are consistent with imp_neto × rate."""
    rate = IVA_ALIQUOTS.get(alicuota_id)
    if rate is None:
        # alicuota_id already flagged by a prior rule — skip amount check
        return True
    expected_iva = (imp_neto * rate).quantize(Decimal("0.01"))
    expected_total = (imp_neto + expected_iva).quantize(Decimal("0.01"))
    iva_ok = abs(imp_iva - expected_iva) <= _AMOUNT_TOLERANCE
    total_ok = abs(imp_total - expected_total) <= _AMOUNT_TOLERANCE
    return iva_ok and total_ok


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_draft(draft: VoucherDraft) -> ValidationReport:
    """Validate *draft* against Argentine fiscal policy rules.

    Returns a :class:`ValidationReport` with ``is_valid=True`` when no
    violations are found.  The function is **pure**: it does not mutate the
    draft or perform any I/O.
    """
    errors: list[ValidationError] = []

    # Rule 1 — cbte_tipo must be a known invoice type
    if str(draft.cbte_tipo) not in INVOICE_TYPES:
        errors.append(
            ValidationError(
                field="cbte_tipo",
                code="UNKNOWN_CBTE_TIPO",
                message=(
                    f"cbte_tipo '{draft.cbte_tipo}' is not a known AFIP invoice type."
                ),
            )
        )

    # Rule 2 — punto_venta must be 1–9999
    if not (1 <= draft.punto_venta <= 9999):
        errors.append(
            ValidationError(
                field="punto_venta",
                code="INVALID_PUNTO_VENTA",
                message=(
                    f"punto_venta must be between 1 and 9999, "
                    f"got {draft.punto_venta}."
                ),
            )
        )

    # Rule 3 — fecha_cbte must be valid YYYYMMDD and not > 5 days in the future
    parsed_date = _parse_fecha_cbte(draft.fecha_cbte)
    if parsed_date is None:
        errors.append(
            ValidationError(
                field="fecha_cbte",
                code="INVALID_DATE_FORMAT",
                message=(
                    f"fecha_cbte '{draft.fecha_cbte}' is not a valid YYYYMMDD date."
                ),
            )
        )
    else:
        today = datetime.now(tz=timezone.utc).date()
        delta = (parsed_date - today).days
        if delta > _MAX_FUTURE_DAYS:
            errors.append(
                ValidationError(
                    field="fecha_cbte",
                    code="DATE_TOO_FAR_IN_FUTURE",
                    message=(
                        f"fecha_cbte '{draft.fecha_cbte}' is {delta} days in the "
                        f"future; maximum allowed is {_MAX_FUTURE_DAYS}."
                    ),
                )
            )

    # Rule 4 — cuit_receptor must pass CUIT check-digit validation
    if not _is_valid_cuit(draft.cuit_receptor):
        errors.append(
            ValidationError(
                field="cuit_receptor",
                code="INVALID_CUIT",
                message=(
                    f"cuit_receptor '{draft.cuit_receptor}' has an invalid "
                    "check digit."
                ),
            )
        )

    # Rule 5 — alicuota_id must exist in IVA_ALIQUOTS
    alicuota_known = draft.alicuota_id in IVA_ALIQUOTS
    if not alicuota_known:
        errors.append(
            ValidationError(
                field="alicuota_id",
                code="UNKNOWN_ALICUOTA",
                message=(
                    f"alicuota_id '{draft.alicuota_id}' is not a known IVA aliquot. "
                    f"Valid values: {', '.join(sorted(IVA_ALIQUOTS))}."
                ),
            )
        )

    # Rule 6 — imp_neto must be >= 0 (also enforced by Pydantic, belt-and-suspenders)
    if draft.imp_neto < Decimal("0"):
        errors.append(
            ValidationError(
                field="imp_neto",
                code="NEGATIVE_IMP_NETO",
                message=f"imp_neto must be >= 0, got {draft.imp_neto}.",
            )
        )

    # Rule 7 — imp_iva and imp_total must be consistent with imp_neto × alicuota_rate
    if alicuota_known and not _amounts_consistent(
        draft.imp_neto,
        draft.alicuota_id,
        draft.imp_iva,
        draft.imp_total,
    ):
        errors.append(
            ValidationError(
                field="imp_total",
                code="INCONSISTENT_AMOUNTS",
                message=(
                    f"imp_iva ({draft.imp_iva}) and/or imp_total ({draft.imp_total}) "
                    f"are inconsistent with imp_neto ({draft.imp_neto}) × "
                    f"alicuota rate ({IVA_ALIQUOTS[draft.alicuota_id]})."
                ),
            )
        )

    return ValidationReport(is_valid=len(errors) == 0, errors=errors)
