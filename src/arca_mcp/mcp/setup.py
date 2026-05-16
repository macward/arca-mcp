"""Tools MCP para diagnóstico de setup WSAA y acceso a servicios."""

from pathlib import Path

import fastmcp

from arca_mcp.wsaa import (
    SetupCheckResult,
    SetupDoctorReport,
    WsaaEnvironment,
    run_setup_doctor,
    validate_service_authorization as _validate_service,
    validate_wsaa_login as _validate_wsaa,
)

server = fastmcp.FastMCP("setup")


@server.tool
def validate_wsaa_login(cert_path: str, key_path: str, service: str = "wsfe") -> SetupCheckResult:
    """Intenta autenticarse con WSAA homologación y verifica que el token sea válido."""
    return _validate_wsaa(
        Path(cert_path),
        Path(key_path),
        service=service,
        environment=WsaaEnvironment.HOMOLOGACION,
    )


@server.tool
def validate_service_authorization(
    cert_path: str, key_path: str, service: str
) -> SetupCheckResult:
    """Verifica que el certificado tenga acceso autorizado a un servicio ARCA.

    Servicios comunes: wsfe (factura electrónica), ws_sr_padron_a4 (padrón),
    wsfex (factura de exportación), wsmtxca (factura con detalle).
    """
    return _validate_service(
        Path(cert_path),
        Path(key_path),
        service=service,
        environment=WsaaEnvironment.HOMOLOGACION,
    )


@server.tool
def setup_doctor(
    cert_path: str, key_path: str, service: str = "wsfe"
) -> SetupDoctorReport:
    """Ejecuta el diagnóstico completo del setup técnico ARCA.

    Corre en secuencia: private_key → certificate → cert_key_match → wsaa_login →
    service_authorization. Si algo falla, los checks downstream se marcan como
    `skipped` para que sepas exactamente cuál es el problema.

    Retorna un reporte con la lista de checks y el campo `failed_check` apuntando
    al primer fallo.
    """
    return run_setup_doctor(
        Path(cert_path),
        Path(key_path),
        service=service,
        environment=WsaaEnvironment.HOMOLOGACION,
    )
