"""Tools MCP para diagnóstico de setup WSAA y acceso a servicios."""

from pathlib import Path

import fastmcp

from arca_mcp.config import Environment
from arca_mcp.wsaa import (
    SetupCheckResult,
    SetupDoctorReport,
    WsaaEnvironment,
    run_setup_doctor,
    validate_service_authorization as _validate_service,
    validate_wsaa_login as _validate_wsaa,
)

server = fastmcp.FastMCP("setup")


_ENV_MAP = {
    Environment.HOMOLOGACION: WsaaEnvironment.HOMOLOGACION,
    Environment.PRODUCCION: WsaaEnvironment.PRODUCCION,
}


def _resolve_environment(environment: str) -> WsaaEnvironment:
    try:
        env = Environment(environment)
    except ValueError as exc:
        valid = ", ".join(member.value for member in Environment)
        raise ValueError(
            f"environment inválido: {environment!r}. Valores válidos: {valid}"
        ) from exc
    return _ENV_MAP[env]


@server.tool
def validate_wsaa_login(
    cert_path: str,
    key_path: str,
    service: str = "wsfe",
    environment: str = "homologacion",
) -> SetupCheckResult:
    """Intenta autenticarse con WSAA y verifica que el token sea válido.

    `environment`: "homologacion" (default) o "produccion".
    """
    return _validate_wsaa(
        Path(cert_path),
        Path(key_path),
        service=service,
        environment=_resolve_environment(environment),
    )


@server.tool
def validate_service_authorization(
    cert_path: str,
    key_path: str,
    service: str,
    environment: str = "homologacion",
) -> SetupCheckResult:
    """Verifica que el certificado tenga acceso autorizado a un servicio ARCA.

    Servicios comunes: wsfe (factura electrónica), ws_sr_padron_a4 (padrón),
    wsfex (factura de exportación), wsmtxca (factura con detalle).

    `environment`: "homologacion" (default) o "produccion".
    """
    return _validate_service(
        Path(cert_path),
        Path(key_path),
        service=service,
        environment=_resolve_environment(environment),
    )


@server.tool
def setup_doctor(
    cert_path: str,
    key_path: str,
    service: str = "wsfe",
    environment: str = "homologacion",
) -> SetupDoctorReport:
    """Ejecuta el diagnóstico completo del setup técnico ARCA.

    Corre en secuencia: private_key → certificate → cert_key_match → wsaa_login →
    service_authorization. Si algo falla, los checks downstream se marcan como
    `skipped` para que sepas exactamente cuál es el problema.

    Retorna un reporte con la lista de checks y el campo `failed_check` apuntando
    al primer fallo.

    `environment`: "homologacion" (default) o "produccion".
    """
    return run_setup_doctor(
        Path(cert_path),
        Path(key_path),
        service=service,
        environment=_resolve_environment(environment),
    )
