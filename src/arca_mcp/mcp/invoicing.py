"""Tools MCP para emisión de comprobantes con flujo draft → validate → confirm."""

from __future__ import annotations

import base64
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import fastmcp

from arca_mcp.audit.emission_log import AuditLog
from arca_mcp.config import resolve_runtime_config
from arca_mcp.errors import ArcaError, ArcaErrorCause
from arca_mcp.invoicing.draft_store import DraftStore
from arca_mcp.invoicing.pdf import ConfirmedVoucherInput, generate_invoice_pdf
from arca_mcp.invoicing.qr import QRPayload, build_qr_url, generate_qr_png
from arca_mcp.invoicing.idempotency import IdempotencyStore
from arca_mcp.invoicing.models import DraftStatus, VoucherDraft
from arca_mcp.policy import invoicing as policy
from arca_mcp.wsaa import WsaaEnvironment, validate_wsaa_login
from arca_mcp.wsaa.models import SetupCheckResult
from arca_mcp.wsfe import client as wsfe_client
from arca_mcp.wsfe.models import FECAESolicitarRequest, FECompConsultarRequest

server = fastmcp.FastMCP("invoicing")

# Module-level singletons — same pattern as TokenCache in wsaa.
_draft_store = DraftStore()
_idempotency_store = IdempotencyStore()
_audit_log = AuditLog(Path(os.environ.get("ARCA_AUDIT_LOG_PATH", "/tmp/arca_audit.jsonl")))

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
async def generate_qr(
    fecha: str,
    cuit: str,
    ptoVta: int,
    tipoCmp: int,
    nroCmp: int,
    importe: float,
    moneda: str,
    ctz: float,
    tipoDocRec: int,
    nroDocRec: str,
    codAut: str,
) -> dict:
    """Genera el código QR AFIP para un comprobante confirmado.

    Operación local pura — no requiere WSAA ni certificado.
    Retorna la URL del QR y la imagen PNG codificada en Base64.

    Args:
        fecha: Fecha del comprobante en formato YYYY-MM-DD.
        cuit: CUIT del emisor (11 dígitos).
        ptoVta: Número de punto de venta.
        tipoCmp: Tipo de comprobante.
        nroCmp: Número del comprobante.
        importe: Importe total del comprobante.
        moneda: Código de moneda (ej: "PES").
        ctz: Cotización de la moneda.
        tipoDocRec: Tipo de documento del receptor.
        nroDocRec: Número de documento del receptor.
        codAut: CAE de 14 dígitos numéricos.
    """
    try:
        payload = QRPayload(
            fecha=fecha,
            cuit=cuit,
            ptoVta=ptoVta,
            tipoCmp=tipoCmp,
            nroCmp=nroCmp,
            importe=importe,
            moneda=moneda,
            ctz=ctz,
            tipoDocRec=tipoDocRec,
            nroDocRec=nroDocRec,
            codAut=codAut,
        )
    except Exception as exc:  # noqa: BLE001 — Pydantic ValidationError
        msg = str(exc)
        cause = ArcaErrorCause.INVALID_CAE if "codAut" in msg else ArcaErrorCause.INVALID_CATALOG_VALUE
        return {"error": {"cause": cause, "message": msg}}

    url_result = build_qr_url(payload)
    if isinstance(url_result, ArcaError):
        return {"error": url_result.model_dump()}

    try:
        qr_png = generate_qr_png(payload)
    except Exception as exc:  # noqa: BLE001
        return {"error": {"cause": ArcaErrorCause.ARCA_SERVICE_ERROR, "message": str(exc)}}

    return {
        "qr_url": url_result,
        "qr_png_b64": base64.b64encode(qr_png).decode(),
    }


@server.tool
async def generate_invoice_pdf_tool(
    cbte_tipo: int,
    punto_venta: int,
    cbte_nro: int,
    fecha_cbte: str,
    cae: str,
    cae_fch_vto: str,
    imp_neto: str,
    alicuota_id: str,
    cuit_emisor: str,
    emisor_razon_social: str,
    emisor_domicilio: str,
    cuit_receptor: str,
    doc_tipo: int,
    moneda: str = "PES",
    ctz: float = 1.0,
    nro_doc_receptor: str | None = None,
    receptor_razon_social: str | None = None,
) -> dict:
    """Genera el PDF de una factura electrónica confirmada con QR AFIP embebido.

    Operación local pura — no requiere WSAA ni certificado.
    Retorna el PDF en Base64 y el nombre de archivo sugerido.

    Args:
        cbte_tipo: Tipo de comprobante (ej: 1=Factura A, 6=Factura B).
        punto_venta: Número de punto de venta.
        cbte_nro: Número del comprobante confirmado.
        fecha_cbte: Fecha del comprobante en formato YYYYMMDD.
        cae: CAE de 14 dígitos numéricos.
        cae_fch_vto: Fecha de vencimiento del CAE en formato YYYYMMDD.
        imp_neto: Importe neto gravado como string.
        alicuota_id: Identificador de alícuota IVA (ej: "5" = 21%).
        cuit_emisor: CUIT del emisor (11 dígitos).
        emisor_razon_social: Razón social del emisor.
        emisor_domicilio: Domicilio fiscal del emisor.
        cuit_receptor: CUIT del receptor (11 dígitos).
        doc_tipo: Tipo de documento del receptor (80=CUIT, 96=DNI, 99=Consumidor Final).
        moneda: Código de moneda (default "PES").
        ctz: Cotización de la moneda (default 1.0).
        nro_doc_receptor: Número de documento del receptor para el QR. Auto-derivado si None:
            doc_tipo=80 → cuit_receptor, doc_tipo=99 → "0". Requerido para otros doc_tipo.
        receptor_razon_social: Razón social del receptor (opcional).
    """
    try:
        imp_neto_decimal = Decimal(imp_neto)
    except InvalidOperation:
        return {
            "error": ArcaError(
                cause=ArcaErrorCause.INVALID_CATALOG_VALUE,
                message=f"imp_neto no es un número válido: {imp_neto!r}",
            ).model_dump()
        }

    try:
        voucher = ConfirmedVoucherInput(
            cbte_tipo=cbte_tipo,
            punto_venta=punto_venta,
            cbte_nro=cbte_nro,
            fecha_cbte=fecha_cbte,
            cae=cae,
            cae_fch_vto=cae_fch_vto,
            imp_neto=imp_neto_decimal,
            alicuota_id=alicuota_id,
            moneda=moneda,
            ctz=ctz,
            cuit_emisor=cuit_emisor,
            emisor_razon_social=emisor_razon_social,
            emisor_domicilio=emisor_domicilio,
            cuit_receptor=cuit_receptor,
            doc_tipo=doc_tipo,
            nro_doc_receptor=nro_doc_receptor,
            receptor_razon_social=receptor_razon_social,
        )
    except Exception as exc:  # noqa: BLE001 — Pydantic ValidationError
        return {
            "error": ArcaError(
                cause=ArcaErrorCause.INVALID_CATALOG_VALUE,
                message=str(exc),
            ).model_dump()
        }

    try:
        pdf_bytes = generate_invoice_pdf(voucher)
    except Exception as exc:  # noqa: BLE001
        return {
            "error": ArcaError(
                cause=ArcaErrorCause.ARCA_SERVICE_ERROR,
                message=str(exc),
            ).model_dump()
        }

    # cbte_tipo is intentionally not zero-padded; punto_venta and cbte_nro are.
    filename = f"factura_{cbte_tipo}_{punto_venta:05d}_{cbte_nro:08d}.pdf"
    return {
        "pdf_b64": base64.b64encode(pdf_bytes).decode(),
        "filename": filename,
    }


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
async def confirm_voucher_creation(draft_id: str, idempotency_key: str) -> dict:
    """Confirma la emisión de un comprobante a partir de un draft VALIDADO.

    Solicita el CAE a WSFE (FECAESolicitar) y registra la operación en el
    audit log. Solo se puede confirmar un draft en estado VALIDATED.
    Requiere idempotency_key para prevenir doble emisión ante reintentos.

    La configuración (cert, key, ambiente, CUIT) se toma de las variables de
    entorno ARCA_CERT_PATH, ARCA_KEY_PATH, ARCA_ENVIRONMENT y ARCA_CUIT.

    Args:
        draft_id: UUID del draft a confirmar (debe estar en estado VALIDATED).
        idempotency_key: Clave única de idempotencia para evitar doble emisión.
    """
    _CONFIRMING = {"status": "CONFIRMING"}
    _IN_PROGRESS_ERROR = {
        "error": {
            "cause": "EMISSION_IN_PROGRESS",
            "message": (
                "Una emisión con esta clave de idempotencia ya está en curso. "
                "Reintentá en unos segundos."
            ),
        }
    }

    # Step 1: Check idempotency — a retry with the same key always returns the
    # cached result. A CONFIRMING sentinel means a concurrent emission is in
    # flight; return a clear error instead of the raw sentinel dict.
    existing = await _idempotency_store.get(idempotency_key)
    if existing is not None:
        if existing.get("status") == "CONFIRMING":
            return _IN_PROGRESS_ERROR
        return existing

    # Step 2: Atomically claim the key before any I/O.
    # set_if_absent is a single lock acquisition — no gap between the check
    # and the write, so two concurrent callers can't both proceed.
    claimed = await _idempotency_store.set_if_absent(idempotency_key, _CONFIRMING)
    if not claimed:
        return _IN_PROGRESS_ERROR

    # From here every early-return path must release the claim via delete()
    # so the caller can retry with the same key after fixing the error.

    # Step 3: Retrieve draft
    draft = await _draft_store.get(draft_id)
    if draft is None:
        await _idempotency_store.delete(idempotency_key)
        return {
            "error": {
                "cause": "DRAFT_NOT_FOUND",
                "message": f"No se encontró el draft con id '{draft_id}'.",
            }
        }

    # Step 4: Verify draft is VALIDATED
    if draft.status != DraftStatus.VALIDATED:
        await _idempotency_store.delete(idempotency_key)
        return {
            "error": {
                "cause": "DRAFT_NOT_VALIDATED",
                "message": (
                    f"Draft must be VALIDATED before confirmation. "
                    f"Current status: {draft.status}"
                ),
            }
        }

    # Step 5: Resolve RuntimeConfig
    config = resolve_runtime_config()
    if isinstance(config, ArcaError):
        await _idempotency_store.delete(idempotency_key)
        return config.model_dump()

    emitter_cuit = _require_emitter_cuit(config.emitter_cuit)
    if isinstance(emitter_cuit, ArcaError):
        await _idempotency_store.delete(idempotency_key)
        return emitter_cuit.model_dump()

    # Step 6: Get WSAA token
    token_result = await _get_wsaa_token(
        config.cert_path,
        config.key_path,
        config.environment,
        service="wsfe",
        cuit=emitter_cuit,
    )
    if isinstance(token_result, ArcaError):
        await _idempotency_store.delete(idempotency_key)
        return token_result.model_dump()

    token, sign = token_result

    # Step 7: Call fecae_solicitar — sentinel is already in place
    fecae_request = FECAESolicitarRequest(
        cuit=emitter_cuit,
        punto_venta=draft.punto_venta,
        cbte_tipo=draft.cbte_tipo,
        fecha_cbte=draft.fecha_cbte,
        cuit_receptor=draft.cuit_receptor,
        doc_tipo=draft.doc_tipo,
        imp_neto=draft.imp_neto,
        imp_iva=draft.imp_iva,
        imp_total=draft.imp_total,
        alicuota_id=draft.alicuota_id,
    )
    wsfe_result = wsfe_client.fecae_solicitar(
        token=token,
        sign=sign,
        environment=config.environment,
        request=fecae_request,
    )
    if isinstance(wsfe_result, ArcaError):
        await _idempotency_store.delete(idempotency_key)
        return wsfe_result.model_dump()

    if wsfe_result.resultado == "R":
        await _idempotency_store.delete(idempotency_key)
        obs_msg = "; ".join(wsfe_result.observaciones) if wsfe_result.observaciones else "sin observaciones"
        return {
            "error": {
                "cause": "WSFE_REJECTED",
                "message": f"WSFEv1 rechazó el comprobante. Observaciones: {obs_msg}",
            }
        }

    # Step 8: Write to audit log
    await _audit_log.append(
        {
            "draft_id": draft_id,
            "cuit": emitter_cuit,
            "cbte_nro": wsfe_result.cbte_nro,
            "cae": wsfe_result.cae,
            "idempotency_key": idempotency_key,
        }
    )

    # Step 9: Update draft status to CONFIRMED
    await _draft_store.update_status(draft_id, DraftStatus.CONFIRMED)

    # Step 10: Overwrite sentinel with the real result
    result = {
        "cae": wsfe_result.cae,
        "cbte_nro": wsfe_result.cbte_nro,
        "cae_fch_vto": wsfe_result.cae_fch_vto,
        "draft_id": draft_id,
        "idempotency_key": idempotency_key,
    }
    await _idempotency_store.set(idempotency_key, result)

    return result


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

    if draft.status != DraftStatus.PENDING:
        return {
            "error": {
                "cause": "DRAFT_INVALID_STATUS",
                "message": (
                    f"validate_voucher_draft requires a PENDING draft. "
                    f"Current status: {draft.status}"
                ),
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
