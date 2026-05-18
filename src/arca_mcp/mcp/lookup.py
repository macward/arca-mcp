"""Tools MCP para consultas de catálogos WSFEv1 (FEParamGet*) y padrón A4."""

from __future__ import annotations

import fastmcp

from arca_mcp.config import resolve_runtime_config
from arca_mcp.errors import ArcaError, ArcaErrorCause
from arca_mcp.padron import client as padron_client
from arca_mcp.padron.models import PersonaDetails, TaxpayerStatus
from arca_mcp.validation import catalogs
from arca_mcp.wsfe import client as wsfe_client
from arca_mcp.wsfe.models import CatalogItem
from arca_mcp.wsaa import WsaaEnvironment, validate_wsaa_login
from arca_mcp.wsaa.models import SetupCheckResult

server = fastmcp.FastMCP("lookup")


_ENV_MAP = {
    "homologacion": WsaaEnvironment.HOMOLOGACION,
    "produccion": WsaaEnvironment.PRODUCCION,
}


def _get_wsaa_token(
    cert_path,
    key_path,
    environment: str,
) -> tuple[str, str] | ArcaError:
    """Obtiene token y sign de WSAA para el servicio wsfe.

    Retorna (token, sign) si el login es exitoso, o ArcaError si falla.
    """
    wsaa_env = _ENV_MAP.get(environment, WsaaEnvironment.HOMOLOGACION)
    result: SetupCheckResult = validate_wsaa_login(
        cert_path,
        key_path,
        service="wsfe",
        environment=wsaa_env,
    )
    if not result.ok or result.token is None:
        return ArcaError(
            cause=ArcaErrorCause.WSAA_AUTH_FAILED,
            message=result.message or "WSAA login falló sin mensaje de error.",
        )
    return result.token.token, result.token.sign


@server.tool
def get_voucher_types() -> list[CatalogItem] | ArcaError:
    """Retorna los tipos de comprobante disponibles en WSFEv1.

    Ejemplos: Factura A (1), Factura B (6), Nota de Crédito A (3), etc.
    No requiere parámetros: la configuración (cert, key, ambiente) se toma de
    las variables de entorno ARCA_CERT_PATH, ARCA_KEY_PATH y ARCA_ENVIRONMENT.
    """
    config = resolve_runtime_config()
    if isinstance(config, ArcaError):
        return config
    token_result = _get_wsaa_token(config.cert_path, config.key_path, config.environment)
    if isinstance(token_result, ArcaError):
        return token_result
    token, sign = token_result
    return wsfe_client.get_voucher_types(token, sign, config.environment)


@server.tool
def get_document_types() -> list[CatalogItem] | ArcaError:
    """Retorna los tipos de documento soportados por WSFEv1.

    Ejemplos: DNI (96), CUIT (80), Pasaporte (94), etc.
    No requiere parámetros: la configuración (cert, key, ambiente) se toma de
    las variables de entorno ARCA_CERT_PATH, ARCA_KEY_PATH y ARCA_ENVIRONMENT.
    """
    config = resolve_runtime_config()
    if isinstance(config, ArcaError):
        return config
    token_result = _get_wsaa_token(config.cert_path, config.key_path, config.environment)
    if isinstance(token_result, ArcaError):
        return token_result
    token, sign = token_result
    return wsfe_client.get_document_types(token, sign, config.environment)


@server.tool
def get_tax_types() -> list[CatalogItem] | ArcaError:
    """Retorna los tipos de tributo disponibles en WSFEv1.

    Ejemplos: IVA (1), Impuestos Nacionales (2), Impuestos Provinciales (3), etc.
    No requiere parámetros: la configuración (cert, key, ambiente) se toma de
    las variables de entorno ARCA_CERT_PATH, ARCA_KEY_PATH y ARCA_ENVIRONMENT.
    """
    config = resolve_runtime_config()
    if isinstance(config, ArcaError):
        return config
    token_result = _get_wsaa_token(config.cert_path, config.key_path, config.environment)
    if isinstance(token_result, ArcaError):
        return token_result
    token, sign = token_result
    return wsfe_client.get_tax_types(token, sign, config.environment)


@server.tool
def get_aliquot_types() -> list[CatalogItem] | ArcaError:
    """Retorna las alícuotas de IVA disponibles en WSFEv1.

    Ejemplos: 21% (5), 10.5% (4), 27% (6), Exento (3), etc.
    No requiere parámetros: la configuración (cert, key, ambiente) se toma de
    las variables de entorno ARCA_CERT_PATH, ARCA_KEY_PATH y ARCA_ENVIRONMENT.
    """
    config = resolve_runtime_config()
    if isinstance(config, ArcaError):
        return config
    token_result = _get_wsaa_token(config.cert_path, config.key_path, config.environment)
    if isinstance(token_result, ArcaError):
        return token_result
    token, sign = token_result
    return wsfe_client.get_aliquot_types(token, sign, config.environment)


@server.tool
def get_currency_types() -> list[CatalogItem] | ArcaError:
    """Retorna las monedas disponibles en WSFEv1.

    Ejemplos: Pesos Argentinos (PES), Dólar EEUU (DOL), Euro (060), etc.
    No requiere parámetros: la configuración (cert, key, ambiente) se toma de
    las variables de entorno ARCA_CERT_PATH, ARCA_KEY_PATH y ARCA_ENVIRONMENT.
    """
    config = resolve_runtime_config()
    if isinstance(config, ArcaError):
        return config
    token_result = _get_wsaa_token(config.cert_path, config.key_path, config.environment)
    if isinstance(token_result, ArcaError):
        return token_result
    token, sign = token_result
    return wsfe_client.get_currency_types(token, sign, config.environment)


def _get_padron_wsaa_token(
    cert_path,
    key_path,
    environment: str,
) -> tuple[str, str] | ArcaError:
    """Obtiene token y sign de WSAA para el servicio ws_sr_padron_a4.

    Retorna (token, sign) si el login es exitoso, o ArcaError si falla.
    """
    wsaa_env = _ENV_MAP.get(environment, WsaaEnvironment.HOMOLOGACION)
    result: SetupCheckResult = validate_wsaa_login(
        cert_path,
        key_path,
        service="ws_sr_padron_a4",
        environment=wsaa_env,
    )
    if not result.ok or result.token is None:
        return ArcaError(
            cause=ArcaErrorCause.WSAA_AUTH_FAILED,
            message=result.message or "WSAA login falló sin mensaje de error.",
        )
    return result.token.token, result.token.sign


@server.tool
def get_taxpayer_details(cuit: str) -> PersonaDetails | ArcaError:
    """Retorna los datos completos de un contribuyente del padrón ARCA A4.

    Incluye denominación, estado (ACTIVO/INACTIVO), domicilio fiscal y
    actividades AFIP registradas para el CUIT consultado.

    Args:
        cuit: CUIT del contribuyente a consultar (sin guiones).
    """
    config = resolve_runtime_config()
    if isinstance(config, ArcaError):
        return config
    token_result = _get_padron_wsaa_token(config.cert_path, config.key_path, config.environment)
    if isinstance(token_result, ArcaError):
        return token_result
    token, sign = token_result
    return padron_client.get_persona(
        token=token,
        sign=sign,
        emitter_cuit=config.emitter_cuit or cuit,
        query_cuit=cuit,
        environment=config.environment,
    )


@server.tool
def validate_taxpayer_status(cuit: str) -> TaxpayerStatus | ArcaError:
    """Verifica si un contribuyente está activo en el padrón ARCA A4.

    Retorna un resumen compacto con el estado activo/inactivo del CUIT
    sin exponer todos los datos del padrón.

    Args:
        cuit: CUIT del contribuyente a verificar (sin guiones).
    """
    config = resolve_runtime_config()
    if isinstance(config, ArcaError):
        return config
    token_result = _get_padron_wsaa_token(config.cert_path, config.key_path, config.environment)
    if isinstance(token_result, ArcaError):
        return token_result
    token, sign = token_result
    persona_result = padron_client.get_persona(
        token=token,
        sign=sign,
        emitter_cuit=config.emitter_cuit or cuit,
        query_cuit=cuit,
        environment=config.environment,
    )
    if isinstance(persona_result, ArcaError):
        return persona_result
    return TaxpayerStatus(
        cuit=persona_result.cuit,
        active=persona_result.status == "ACTIVO",
        status_description=persona_result.status,
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
