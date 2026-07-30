"""Tools MCP para consultas de catálogos WSFEv1 (FEParamGet*) y padrón A4."""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Callable

import fastmcp

from arca_mcp.config import resolve_runtime_config
from arca_mcp.errors import ArcaError
from arca_mcp.mcp._auth import get_wsaa_token as _get_wsaa_token
from arca_mcp.mcp._auth import require_emitter_cuit as _require_emitter_cuit
from arca_mcp.padron import client as padron_client
from arca_mcp.padron.models import PersonaDetails, TaxpayerStatus
from arca_mcp.validation import catalogs
from arca_mcp.wsfe import catalog_cache
from arca_mcp.wsfe import client as wsfe_client
from arca_mcp.wsfe.models import CatalogItem

server = fastmcp.FastMCP("lookup")


async def _call_wsfe_catalog(wsfe_fn: Callable) -> list[CatalogItem] | ArcaError:
    """Pipeline config → cache hit / WSAA → WSFEv1 para consultas de catálogo."""
    config = resolve_runtime_config()
    if isinstance(config, ArcaError):
        return config

    cached = catalog_cache.get(wsfe_fn, config.environment)
    if cached is not None:
        return cached

    emitter_cuit = _require_emitter_cuit(config.emitter_cuit)
    if isinstance(emitter_cuit, ArcaError):
        return emitter_cuit
    token_result = await _get_wsaa_token(
        config.cert_path, config.key_path, config.environment, service="wsfe", cuit=emitter_cuit
    )
    if isinstance(token_result, ArcaError):
        return token_result
    token, sign = token_result
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None, functools.partial(wsfe_fn, token, sign, config.environment, emitter_cuit)
    )
    if not isinstance(result, ArcaError):
        catalog_cache.set(wsfe_fn, config.environment, result)
    return result


@server.tool
async def get_voucher_types() -> list[CatalogItem] | ArcaError:
    """Retorna los tipos de comprobante disponibles en WSFEv1.

    Ejemplos: Factura A (1), Factura B (6), Nota de Crédito A (3), etc.
    No requiere parámetros: la configuración (cert, key, ambiente) se toma de
    las variables de entorno ARCA_CERT_PATH, ARCA_KEY_PATH y ARCA_ENVIRONMENT.
    """
    return await _call_wsfe_catalog(wsfe_client.get_voucher_types)


@server.tool
async def get_document_types() -> list[CatalogItem] | ArcaError:
    """Retorna los tipos de documento soportados por WSFEv1.

    Ejemplos: DNI (96), CUIT (80), Pasaporte (94), etc.
    No requiere parámetros: la configuración (cert, key, ambiente) se toma de
    las variables de entorno ARCA_CERT_PATH, ARCA_KEY_PATH y ARCA_ENVIRONMENT.
    """
    return await _call_wsfe_catalog(wsfe_client.get_document_types)


@server.tool
async def get_tax_types() -> list[CatalogItem] | ArcaError:
    """Retorna los tipos de tributo disponibles en WSFEv1.

    Ejemplos: IVA (1), Impuestos Nacionales (2), Impuestos Provinciales (3), etc.
    No requiere parámetros: la configuración (cert, key, ambiente) se toma de
    las variables de entorno ARCA_CERT_PATH, ARCA_KEY_PATH y ARCA_ENVIRONMENT.
    """
    return await _call_wsfe_catalog(wsfe_client.get_tax_types)


@server.tool
async def get_aliquot_types() -> list[CatalogItem] | ArcaError:
    """Retorna las alícuotas de IVA disponibles en WSFEv1.

    Ejemplos: 21% (5), 10.5% (4), 27% (6), Exento (3), etc.
    No requiere parámetros: la configuración (cert, key, ambiente) se toma de
    las variables de entorno ARCA_CERT_PATH, ARCA_KEY_PATH y ARCA_ENVIRONMENT.
    """
    return await _call_wsfe_catalog(wsfe_client.get_aliquot_types)


@server.tool
async def get_currency_types() -> list[CatalogItem] | ArcaError:
    """Retorna las monedas disponibles en WSFEv1.

    Ejemplos: Pesos Argentinos (PES), Dólar EEUU (DOL), Euro (060), etc.
    No requiere parámetros: la configuración (cert, key, ambiente) se toma de
    las variables de entorno ARCA_CERT_PATH, ARCA_KEY_PATH y ARCA_ENVIRONMENT.
    """
    return await _call_wsfe_catalog(wsfe_client.get_currency_types)


@server.tool
async def get_taxpayer_details(cuit: str) -> PersonaDetails | ArcaError:
    """Retorna los datos completos de un contribuyente del padrón ARCA A4.

    Incluye denominación, estado (ACTIVO/INACTIVO), domicilio fiscal y
    actividades AFIP registradas para el CUIT consultado.

    Args:
        cuit: CUIT del contribuyente a consultar (sin guiones).
    """
    config = resolve_runtime_config()
    if isinstance(config, ArcaError):
        return config
    emitter_cuit = _require_emitter_cuit(config.emitter_cuit)
    if isinstance(emitter_cuit, ArcaError):
        return emitter_cuit
    token_result = await _get_wsaa_token(
        config.cert_path, config.key_path, config.environment, service="ws_sr_padron_a4", cuit=emitter_cuit
    )
    if isinstance(token_result, ArcaError):
        return token_result
    token, sign = token_result
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        functools.partial(
            padron_client.get_persona,
            token=token,
            sign=sign,
            emitter_cuit=emitter_cuit,
            query_cuit=cuit,
            environment=config.environment,
        ),
    )


@server.tool
async def validate_taxpayer_status(cuit: str) -> TaxpayerStatus | ArcaError:
    """Verifica si un contribuyente está activo en el padrón ARCA A4.

    Retorna un resumen compacto con el estado activo/inactivo del CUIT
    sin exponer todos los datos del padrón.

    Args:
        cuit: CUIT del contribuyente a verificar (sin guiones).
    """
    config = resolve_runtime_config()
    if isinstance(config, ArcaError):
        return config
    emitter_cuit = _require_emitter_cuit(config.emitter_cuit)
    if isinstance(emitter_cuit, ArcaError):
        return emitter_cuit
    token_result = await _get_wsaa_token(
        config.cert_path, config.key_path, config.environment, service="ws_sr_padron_a4", cuit=emitter_cuit
    )
    if isinstance(token_result, ArcaError):
        return token_result
    token, sign = token_result
    loop = asyncio.get_running_loop()
    persona_result = await loop.run_in_executor(
        None,
        functools.partial(
            padron_client.get_persona,
            token=token,
            sign=sign,
            emitter_cuit=emitter_cuit,
            query_cuit=cuit,
            environment=config.environment,
        ),
    )
    if isinstance(persona_result, ArcaError):
        return persona_result

    _ACTIVE_STATUSES = {"ACTIVO"}
    _STATUS_LABELS: dict[str, str] = {
        "ACTIVO": "Activo",
        "INACTIVO": "Inactivo",
        "CANCELADO": "Cancelado por AFIP",
        "BLOQUEADO": "Bloqueado",
        "CLAUSURADO": "Clausurado",
    }
    raw = persona_result.status
    label = _STATUS_LABELS.get(raw, raw)
    return TaxpayerStatus(
        cuit=persona_result.cuit,
        active=raw in _ACTIVE_STATUSES,
        status_description=label,
    )


@server.tool
def validate_invoice_type(invoice_type: str) -> dict:
    """Valida si un tipo de comprobante es válido según catálogo AFIP.

    No requiere certificado ni conexión a ARCA — validación 100% local.

    Args:
        invoice_type: Código numérico del tipo de comprobante (ej: "1" para Factura A).
    """
    valid = catalogs.is_valid_invoice_type(invoice_type)
    return {"invoice_type": invoice_type, "valid": valid}


@server.tool
def validate_vat_condition(vat_condition: str) -> dict:
    """Valida si una condición frente al IVA es válida según catálogo AFIP.

    No requiere certificado ni conexión a ARCA — validación 100% local.

    Args:
        vat_condition: Código numérico de la condición IVA (ej: "1" para Responsable Inscripto).
    """
    valid = catalogs.is_valid_vat_condition(vat_condition)
    return {"vat_condition": vat_condition, "valid": valid}


@server.tool
def validate_currency(currency: str) -> dict:
    """Valida si un código de moneda es válido según catálogo AFIP.

    No requiere certificado ni conexión a ARCA — validación 100% local.

    Args:
        currency: Código de moneda AFIP (ej: "PES" para Pesos, "DOL" para Dólar).
    """
    valid = catalogs.is_valid_currency(currency)
    return {"currency": currency, "valid": valid}
