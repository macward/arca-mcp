from decimal import Decimal

from pydantic import BaseModel


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


class FECAESolicitarResponse(BaseModel):
    cae: str
    cbte_nro: int
    cae_fch_vto: str  # YYYYMMDD
    resultado: str  # A=Aprobado, R=Rechazado
    observaciones: list[str]


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
