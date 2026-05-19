"""Tools MCP para emisión de comprobantes con flujo draft → validate → confirm."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import fastmcp

from arca_mcp.config import resolve_runtime_config
from arca_mcp.errors import ArcaError, ArcaErrorCause
from arca_mcp.invoicing.draft_store import DraftStore
from arca_mcp.invoicing.models import DraftStatus, VoucherDraft
from arca_mcp.policy import invoicing as policy
from arca_mcp.wsaa import WsaaEnvironment, validate_wsaa_login
from arca_mcp.wsaa.models import SetupCheckResult
from arca_mcp.wsfe import client as wsfe_client
from arca_mcp.wsfe.models import FECompConsultarRequest

server = fastmcp.FastMCP("invoicing")

# Module-level singleton — same pattern as TokenCache in wsaa.
_draft_store = DraftStore()

_ENV_MAP = {
    "homologacion": WsaaEnvironment.HOMOLOGACION,
    "produccion": WsaaEnvironment.PRODUCCION,
}


async def _get_wsaa_token(
    cert_path,
    key_path,
    environment: str,
    service: str,
    cuit: str | None = None,
) -> tuple[str, str] | ArcaError:
    """Obtiene token y sign de WSAA para el servicio indicado."""
    wsaa_env = _ENV_MAP.get(environment, WsaaEnvironment.HOMOLOGACION)
    result: SetupCheckResult = await validate_wsaa_login(
        cert_path,
        key_path,
        service=service,
        environment=wsaa_env,
        cuit=cuit,
    )
    if not result.ok or result.token is None:
        return ArcaError(
            cause=ArcaErrorCause.WSAA_AUTH_FAILED,
            message=result.message or "WSAA login falló sin mensaje de error.",
        )
    return result.token.token, result.token.sign


def _require_emitter_cuit(emitter_cuit: str | None) -> str | ArcaError:
    """Retorna CUIT emisor configurado o error estructurado."""
    if emitter_cuit is None or not emitter_cuit.strip():
        return ArcaError(
            cause=ArcaErrorCause.MISSING_CONFIG,
            message=(
                "ARCA_CUIT no está configurado. "
                "Las consultas autenticadas a ARCA requieren cuitRepresentada/Cuit."
            ),
        )
    cuit = emitter_cuit.strip()
    if not cuit.isdigit():
        return ArcaError(
            cause=ArcaErrorCause.MISSING_CONFIG,
            message=f"ARCA_CUIT debe contener solo dígitos: {emitter_cuit!r}",
        )
    return cuit


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


@server.tool
async def get_last_voucher_number(punto_venta: int, cbte_tipo: int) -> dict:
    """Retorna el último número de comprobante autorizado para un punto de venta y tipo.

    Útil para determinar el próximo número de comprobante a emitir.
    La configuración (cert, key, ambiente, CUIT) se toma de las variables de entorno
    ARCA_CERT_PATH, ARCA_KEY_PATH, ARCA_ENVIRONMENT y ARCA_CUIT.

    Args:
        punto_venta: Número de punto de venta habilitado en ARCA.
        cbte_tipo: Tipo de comprobante (ej: 1=Factura A, 6=Factura B).
    """
    config = resolve_runtime_config()
    if isinstance(config, ArcaError):
        return config.model_dump()

    emitter_cuit = _require_emitter_cuit(config.emitter_cuit)
    if isinstance(emitter_cuit, ArcaError):
        return emitter_cuit.model_dump()

    token_result = await _get_wsaa_token(
        config.cert_path, config.key_path, config.environment, service="wsfe", cuit=emitter_cuit
    )
    if isinstance(token_result, ArcaError):
        return token_result.model_dump()

    token, sign = token_result
    result = wsfe_client.fecomp_ultimo_autorizado(
        token=token,
        sign=sign,
        environment=config.environment,
        cuit=emitter_cuit,
        punto_venta=punto_venta,
        cbte_tipo=cbte_tipo,
    )
    if isinstance(result, ArcaError):
        return result.model_dump()

    return {"cbte_nro": result.cbte_nro}


@server.tool
async def get_voucher_info(punto_venta: int, cbte_tipo: int, cbte_nro: int) -> dict:
    """Retorna los datos de un comprobante específico registrado en WSFEv1.

    Incluye CAE, fechas, importes y receptor del comprobante consultado.
    La configuración (cert, key, ambiente, CUIT) se toma de las variables de entorno
    ARCA_CERT_PATH, ARCA_KEY_PATH, ARCA_ENVIRONMENT y ARCA_CUIT.

    Args:
        punto_venta: Número de punto de venta del comprobante.
        cbte_tipo: Tipo de comprobante (ej: 1=Factura A, 6=Factura B).
        cbte_nro: Número del comprobante a consultar.
    """
    config = resolve_runtime_config()
    if isinstance(config, ArcaError):
        return config.model_dump()

    emitter_cuit = _require_emitter_cuit(config.emitter_cuit)
    if isinstance(emitter_cuit, ArcaError):
        return emitter_cuit.model_dump()

    token_result = await _get_wsaa_token(
        config.cert_path, config.key_path, config.environment, service="wsfe", cuit=emitter_cuit
    )
    if isinstance(token_result, ArcaError):
        return token_result.model_dump()

    token, sign = token_result
    request = FECompConsultarRequest(
        cuit=emitter_cuit,
        punto_venta=punto_venta,
        cbte_tipo=cbte_tipo,
        cbte_nro=cbte_nro,
    )
    result = wsfe_client.fecomp_consultar(
        token=token,
        sign=sign,
        environment=config.environment,
        request=request,
    )
    if isinstance(result, ArcaError):
        return result.model_dump()

    return result.model_dump()


@server.tool
async def validate_voucher_draft(draft_id: str) -> dict:
    """Valida un borrador de comprobante contra las reglas de política fiscal.

    Si la validación es exitosa, el draft pasa a estado VALIDATED y queda
    listo para ser confirmado con confirm_voucher_creation.
    Si hay errores, el draft permanece en PENDING y se retornan los detalles
    de cada violación encontrada.

    Args:
        draft_id: Identificador del draft a validar (UUID generado por create_voucher_draft).
    """
    try:
        draft = await _draft_store.get(draft_id)
    except Exception as exc:  # noqa: BLE001
        return {"error": {"cause": "INTERNAL_ERROR", "message": str(exc)}}

    if draft is None:
        return {
            "error": {
                "cause": "DRAFT_NOT_FOUND",
                "message": f"Draft {draft_id} not found",
            }
        }

    try:
        report = policy.validate_draft(draft)
    except Exception as exc:  # noqa: BLE001
        return {"error": {"cause": "INTERNAL_ERROR", "message": str(exc)}}

    if report.is_valid:
        try:
            await _draft_store.update_status(draft_id, DraftStatus.VALIDATED)
        except Exception as exc:  # noqa: BLE001
            return {"error": {"cause": "INTERNAL_ERROR", "message": str(exc)}}
        status = DraftStatus.VALIDATED
    else:
        status = draft.status

    return {
        "draft_id": draft_id,
        "is_valid": report.is_valid,
        "status": status.value,
        "errors": [
            {"field": e.field, "code": e.code, "message": e.message}
            for e in report.errors
        ],
    }
