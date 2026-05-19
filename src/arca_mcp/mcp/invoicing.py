"""Tools MCP para emisión de comprobantes con flujo draft → validate → confirm."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import fastmcp

from arca_mcp.errors import ArcaError, ArcaErrorCause
from arca_mcp.invoicing.draft_store import DraftStore
from arca_mcp.invoicing.models import VoucherDraft

server = fastmcp.FastMCP("invoicing")

# Module-level singleton — same pattern as TokenCache in wsaa.
_draft_store = DraftStore()


@server.tool
async def create_voucher_draft(
    cbte_tipo: int,
    punto_venta: int,
    fecha_cbte: str,
    cuit_receptor: str,
    doc_tipo: int,
    imp_neto: str,
    alicuota_id: str,
) -> dict | ArcaError:
    """Crea un borrador de comprobante (draft) listo para validar y confirmar.

    El borrador queda en estado PENDING y no genera ningún comprobante fiscal
    hasta que se complete el flujo validate_voucher_draft → confirm_voucher_creation.

    Args:
        cbte_tipo: Tipo de comprobante (e.g. 6 = Factura B, 1 = Factura A).
        punto_venta: Número de punto de venta habilitado (1-9999).
        fecha_cbte: Fecha del comprobante en formato YYYYMMDD.
        cuit_receptor: CUIT del receptor sin guiones (11 dígitos).
        doc_tipo: Tipo de documento del receptor (80=CUIT, 86=CUIL, 96=DNI, 99=consumidor final).
        imp_neto: Importe neto gravado como string (se convierte a Decimal internamente).
        alicuota_id: Identificador de alícuota IVA según catálogo ARCA (e.g. "5" = 21%).
    """
    # Parse imp_neto from string to Decimal before passing to Pydantic.
    try:
        imp_neto_decimal = Decimal(imp_neto)
    except InvalidOperation:
        return ArcaError(
            cause=ArcaErrorCause.INVALID_CATALOG_VALUE,
            message=f"imp_neto no es un número válido: {imp_neto!r}",
        )

    now = datetime.now(timezone.utc)

    try:
        draft = VoucherDraft(
            draft_id=str(uuid.uuid4()),
            cbte_tipo=cbte_tipo,
            punto_venta=punto_venta,
            fecha_cbte=fecha_cbte,
            cuit_receptor=cuit_receptor,
            doc_tipo=doc_tipo,
            imp_neto=imp_neto_decimal,
            alicuota_id=alicuota_id,
            created_at=now,
            updated_at=now,
        )
    except Exception as exc:  # noqa: BLE001 — Pydantic ValidationError
        return ArcaError(
            cause=ArcaErrorCause.INVALID_CATALOG_VALUE,
            message=str(exc),
        )

    await _draft_store.create(draft)

    return {
        "draft_id": draft.draft_id,
        "status": draft.status,
        "imp_neto": str(draft.imp_neto),
        "imp_iva": str(draft.imp_iva),
        "imp_total": str(draft.imp_total),
        "created_at": draft.created_at.isoformat(),
    }
