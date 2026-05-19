"""Data models for draft-based invoicing.

Only homologación is supported at this stage. No production logic lives here.
"""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field, computed_field, model_validator

# IVA alicuota rates keyed by alicuota_id as defined in ARCA catalogs.
# https://afip.gob.ar/fe/documentos/manual_developer_COMPG_v2.pdf — Table IVA
_ALICUOTA_RATES: dict[str, Decimal] = {
    "3": Decimal("0"),       # 0 %
    "4": Decimal("0.105"),   # 10.5 %
    "5": Decimal("0.21"),    # 21 %
    "6": Decimal("0.27"),    # 27 %
    "8": Decimal("0.05"),    # 5 %
    "9": Decimal("0.025"),   # 2.5 %
}


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

    # Receptor
    cuit_receptor: str = Field(
        description="CUIT del receptor (sin guiones, 11 dígitos).",
        pattern=r"^\d{11}$",
    )
    doc_tipo: int = Field(description="Tipo de documento del receptor (80 = CUIT).")

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
    def _validate_alicuota(self) -> "VoucherDraft":
        if self.alicuota_id not in _ALICUOTA_RATES:
            valid = ", ".join(sorted(_ALICUOTA_RATES))
            raise ValueError(
                f"alicuota_id '{self.alicuota_id}' is not a known value. "
                f"Valid values: {valid}"
            )
        return self
