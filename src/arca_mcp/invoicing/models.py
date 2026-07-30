"""Data models for draft-based invoicing.

Only homologación is supported at this stage. No production logic lives here.
"""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

from arca_mcp.validation.catalogs import IVA_ALIQUOTS as _ALICUOTA_RATES


class DraftStatus(StrEnum):
    """Lifecycle status of a VoucherDraft.

    Allowed transitions:
      PENDING → VALIDATED
      PENDING → REJECTED
      VALIDATED → CONFIRMED
      VALIDATED → REJECTED
    """

    PENDING = "PENDING"
    VALIDATED = "VALIDATED"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"


class VoucherDraft(BaseModel):
    """Immutable-ish representation of a voucher in progress.

    Fields are set at creation; only `status` and `updated_at` change
    after creation (via DraftStore.update_status).
    """

    draft_id: str = Field(description="UUID identifying this draft.")
    status: DraftStatus = Field(default=DraftStatus.PENDING)

    # Voucher header
    cbte_tipo: int = Field(description="Tipo de comprobante (e.g. 1 = Factura A).")
    punto_venta: int = Field(description="Punto de venta habilitado.")
    fecha_cbte: str = Field(
        description="Fecha del comprobante en formato YYYYMMDD.",
        pattern=r"^\d{8}$",
    )

    @field_validator("fecha_cbte")
    @classmethod
    def _validate_fecha_cbte_calendar(cls, v: str) -> str:
        from datetime import date
        try:
            date.fromisoformat(f"{v[:4]}-{v[4:6]}-{v[6:]}")
        except ValueError:
            raise ValueError(f"fecha_cbte '{v}' is not a valid calendar date.") from None
        return v

    # Receptor
    cuit_receptor: str = Field(
        description=(
            "CUIT del receptor (sin guiones, 11 dígitos). "
            "Para doc_tipo=99 (Consumidor Final) usar '0'."
        ),
    )
    doc_tipo: int = Field(description="Tipo de documento del receptor (80 = CUIT, 99 = Consumidor Final).")

    # Importes
    imp_neto: Decimal = Field(description="Importe neto gravado.", ge=Decimal("0"))
    alicuota_id: str = Field(
        description="Identificador de alícuota de IVA según catálogo ARCA."
    )

    # Timestamps
    created_at: datetime = Field(description="UTC datetime of draft creation.")
    updated_at: datetime = Field(description="UTC datetime of last status update.")

    @computed_field  # type: ignore[misc]
    @property
    def imp_iva(self) -> Decimal:
        """IVA amount computed from imp_neto × alicuota rate."""
        rate = _ALICUOTA_RATES.get(self.alicuota_id, Decimal("0"))
        return (self.imp_neto * rate).quantize(Decimal("0.01"))

    @computed_field  # type: ignore[misc]
    @property
    def imp_total(self) -> Decimal:
        """Total amount = imp_neto + imp_iva."""
        return (self.imp_neto + self.imp_iva).quantize(Decimal("0.01"))

    @model_validator(mode="after")
    def _validate_cuit_receptor(self) -> "VoucherDraft":
        import re
        if self.doc_tipo == 99:
            if self.cuit_receptor != "0":
                raise ValueError(
                    "cuit_receptor must be '0' when doc_tipo=99 (Consumidor Final)."
                )
        elif self.doc_tipo == 96:
            if not re.fullmatch(r"\d{7,8}", self.cuit_receptor):
                raise ValueError(
                    f"cuit_receptor '{self.cuit_receptor}' must be 7-8 digits for doc_tipo=96 (DNI)."
                )
        elif self.doc_tipo == 80:
            if not re.fullmatch(r"\d{11}", self.cuit_receptor):
                raise ValueError(
                    f"cuit_receptor '{self.cuit_receptor}' must be 11 digits for doc_tipo=80 (CUIT)."
                )
        else:
            if not self.cuit_receptor:
                raise ValueError(
                    f"cuit_receptor must not be empty for doc_tipo={self.doc_tipo}."
                )
        return self

    @model_validator(mode="after")
    def _validate_alicuota(self) -> "VoucherDraft":
        if self.alicuota_id not in _ALICUOTA_RATES:
            valid = ", ".join(sorted(_ALICUOTA_RATES))
            raise ValueError(
                f"alicuota_id '{self.alicuota_id}' is not a known value. "
                f"Valid values: {valid}"
            )
        return self
