"""Tools MCP para consultas de catálogos WSFEv1 (FEParamGet*)."""

from __future__ import annotations

import fastmcp

from arca_mcp.config import resolve_runtime_config
from arca_mcp.errors import ArcaError, ArcaErrorCause
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
