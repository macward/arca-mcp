"""Helpers de autenticación compartidos entre tools MCP."""

from __future__ import annotations

from arca_mcp.errors import ArcaError, ArcaErrorCause
from arca_mcp.wsaa import WsaaEnvironment, validate_wsaa_login
from arca_mcp.wsaa.models import SetupCheckResult

_ENV_MAP = {
    "homologacion": WsaaEnvironment.HOMOLOGACION,
    "produccion": WsaaEnvironment.PRODUCCION,
}


async def get_wsaa_token(
    cert_path,
    key_path,
    environment: str,
    service: str,
    cuit: str | None = None,
) -> tuple[str, str] | ArcaError:
    """Obtiene (token, sign) de WSAA para el servicio indicado, o ArcaError si falla."""
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


def require_emitter_cuit(emitter_cuit: str | None) -> str | ArcaError:
    """Retorna CUIT emisor configurado o ArcaError estructurado."""
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
