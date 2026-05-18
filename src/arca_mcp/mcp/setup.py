"""Tools MCP para diagnóstico de setup WSAA y acceso a servicios."""

from __future__ import annotations

import fastmcp

from arca_mcp.config import ConfigOverrides, resolve_runtime_config
from arca_mcp.config_settings import Environment
from arca_mcp.errors import ArcaError
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


def _build_overrides(
    cert_path: str | None,
    key_path: str | None,
    environment: str | None,
) -> ConfigOverrides:
    """Construye ConfigOverrides a partir de strings opcionales."""
    from pathlib import Path

    env: Environment | None = None
    if environment is not None:
        try:
            env = Environment(environment)
        except ValueError:
            valid = ", ".join(member.value for member in Environment)
            raise ValueError(
                f"environment inválido: {environment!r}. Valores válidos: {valid}"
            )
    return ConfigOverrides(
        cert_path=Path(cert_path) if cert_path is not None else None,
        key_path=Path(key_path) if key_path is not None else None,
        environment=env,
    )


@server.tool
def validate_wsaa_login(
    cert_path: str | None = None,
    key_path: str | None = None,
    service: str = "wsfe",
    environment: str = "homologacion",
) -> SetupCheckResult | ArcaError:
    """Intenta autenticarse con WSAA y verifica que el token sea válido.

    `cert_path` y `key_path` son overrides opcionales. Si no se pasan, el
    resolver los toma de Settings (ARCA_CERT_PATH / ARCA_KEY_PATH). Deben
    pasarse juntos o ninguno.

    `environment`: "homologacion" (default) o "produccion".
    """
    config = resolve_runtime_config(_build_overrides(cert_path, key_path, environment))
    if isinstance(config, ArcaError):
        return config
    return _validate_wsaa(
        config.cert_path,
        config.key_path,
        service=service,
        environment=_ENV_MAP[config.environment],
    )


@server.tool
def validate_service_authorization(
    cert_path: str | None = None,
    key_path: str | None = None,
    service: str = "wsfe",
    environment: str = "homologacion",
) -> SetupCheckResult | ArcaError:
    """Verifica que el certificado tenga acceso autorizado a un servicio ARCA.

    Servicios comunes: wsfe (factura electrónica), ws_sr_padron_a4 (padrón),
    wsfex (factura de exportación), wsmtxca (factura con detalle).

    `cert_path` y `key_path` son overrides opcionales. Si no se pasan, el
    resolver los toma de Settings (ARCA_CERT_PATH / ARCA_KEY_PATH). Deben
    pasarse juntos o ninguno.

    `environment`: "homologacion" (default) o "produccion".
    """
    config = resolve_runtime_config(_build_overrides(cert_path, key_path, environment))
    if isinstance(config, ArcaError):
        return config
    return _validate_service(
        config.cert_path,
        config.key_path,
        service=service,
        environment=_ENV_MAP[config.environment],
    )


@server.tool
def setup_doctor(
    cert_path: str | None = None,
    key_path: str | None = None,
    service: str = "wsfe",
    environment: str = "homologacion",
) -> SetupDoctorReport | ArcaError:
    """Ejecuta el diagnóstico completo del setup técnico ARCA.

    Corre en secuencia: private_key → certificate → cert_key_match → wsaa_login →
    service_authorization. Si algo falla, los checks downstream se marcan como
    `skipped` para que sepas exactamente cuál es el problema.

    Retorna un reporte con la lista de checks y el campo `failed_check` apuntando
    al primer fallo.

    `cert_path` y `key_path` son overrides opcionales. Si no se pasan, el
    resolver los toma de Settings (ARCA_CERT_PATH / ARCA_KEY_PATH). Deben
    pasarse juntos o ninguno.

    `environment`: "homologacion" (default) o "produccion".
    """
    config = resolve_runtime_config(_build_overrides(cert_path, key_path, environment))
    if isinstance(config, ArcaError):
        return config
    return run_setup_doctor(
        config.cert_path,
        config.key_path,
        service=service,
        environment=_ENV_MAP[config.environment],
    )
