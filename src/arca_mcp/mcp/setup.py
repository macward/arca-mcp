"""Tools MCP para diagnóstico de setup WSAA y acceso a servicios."""

from pathlib import Path

import fastmcp

from arca_mcp.wsaa import SetupCheckResult, WsaaEnvironment
from arca_mcp.wsaa import validate_wsaa_login as _validate_wsaa

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
    """Verifica que el certificado tenga acceso autorizado a un servicio ARCA."""
    raise NotImplementedError


@server.tool
def setup_doctor(cert_path: str, key_path: str) -> list[SetupCheckResult]:
    """Ejecuta todas las validaciones de setup en secuencia y retorna el diagnóstico completo."""
    raise NotImplementedError
