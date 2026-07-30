from datetime import date
from decimal import Decimal

from pydantic import BaseModel, field_validator


def _validate_yyyymmdd(field_name: str, v: str) -> str:
    if len(v) != 8 or not v.isdigit():
        raise ValueError(f"{field_name} '{v}' must be 8 digits in YYYYMMDD format.")
    try:
        date.fromisoformat(f"{v[:4]}-{v[4:6]}-{v[6:]}")
    except ValueError:
        raise ValueError(f"{field_name} '{v}' is not a valid calendar date.") from None
    return v


class CatalogItem(BaseModel):
    id: str
    description: str


# ---------------------------------------------------------------------------
# FECAESolicitar — solicitud de autorización CAE
# ---------------------------------------------------------------------------


class FECAESolicitarRequest(BaseModel):
    cuit: str
    punto_venta: int
    cbte_tipo: int
    fecha_cbte: str  # YYYYMMDD
    cuit_receptor: str
    doc_tipo: int
    imp_neto: Decimal
    imp_iva: Decimal
    imp_total: Decimal
    alicuota_id: str
    concepto: int = 1  # 1=Productos, 2=Servicios, 3=Productos y Servicios

    @field_validator("fecha_cbte")
    @classmethod
    def _check_fecha_cbte(cls, v: str) -> str:
        return _validate_yyyymmdd("fecha_cbte", v)


class FECAESolicitarResponse(BaseModel):
    cae: str
    cbte_nro: int
    cae_fch_vto: str  # YYYYMMDD
    resultado: str  # A=Aprobado, R=Rechazado
    observaciones: list[str]

    @field_validator("cae_fch_vto")
    @classmethod
    def _check_cae_fch_vto(cls, v: str) -> str:
        return _validate_yyyymmdd("cae_fch_vto", v)


# ---------------------------------------------------------------------------
# FECompUltimoAutorizado — último número de comprobante autorizado
# ---------------------------------------------------------------------------


class FECompUltimoAutorizadoResponse(BaseModel):
    cbte_nro: int


# ---------------------------------------------------------------------------
# FECompConsultar — consulta de un comprobante específico
# ---------------------------------------------------------------------------


class FECompConsultarRequest(BaseModel):
    cuit: str
    punto_venta: int
    cbte_tipo: int
    cbte_nro: int


class FECompConsultarResponse(BaseModel):
    cbte_nro: int
    cbte_tipo: int
    punto_venta: int
    cae: str
    cae_fch_vto: str  # YYYYMMDD
    fecha_cbte: str  # YYYYMMDD
    resultado: str
    doc_tipo: int
    doc_nro: str
    imp_total: Decimal
    imp_neto: Decimal
    imp_iva: Decimal

    @field_validator("fecha_cbte")
    @classmethod
    def _check_fecha_cbte(cls, v: str) -> str:
        return _validate_yyyymmdd("fecha_cbte", v)

    @field_validator("cae_fch_vto")
    @classmethod
    def _check_cae_fch_vto(cls, v: str) -> str:
        return _validate_yyyymmdd("cae_fch_vto", v)
