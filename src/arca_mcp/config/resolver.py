"""Resolver central de configuración para arca-mcp.

Fusiona los defaults del servidor (Settings / variables de entorno ARCA_*)
con overrides opcionales por llamada. Retorna una RuntimeConfig validada o
un ArcaError estructurado — nunca lanza excepciones crudas.

Reglas (per brief v0_2_config_model_brief.md):
- Solo HOMOLOGACION está soportado en v0.2.
- cert_path y key_path se overridean JUNTOS o ninguno.
- Si un campo requerido falta en ambas fuentes → MISSING_CONFIG.
- Si se pasa solo cert_path o solo key_path → INVALID_CONFIG_OVERRIDE.
- Si environment == PRODUCCION → UNSUPPORTED_ENVIRONMENT.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

from pydantic import BaseModel, ConfigDict

from arca_mcp.config_settings import Settings, Environment
from arca_mcp.errors import ArcaError, ArcaErrorCause


class RuntimeConfig(BaseModel):
    """Configuración validada e inmutable por llamada MCP.

    Nunca contiene bytes de certificado/key; solo paths al filesystem.
    Determinística y hasheable para derivar cache keys en v0.3.
    """

    model_config = ConfigDict(frozen=True)

    environment: Environment
    cert_path: Path
    key_path: Path
    emitter_cuit: str | None = None

    def __hash__(self) -> int:
        return hash((self.environment, self.cert_path, self.key_path, self.emitter_cuit))


class ConfigOverrides(BaseModel):
    """Overrides opcionales por llamada. Todos los campos son opcionales."""

    cert_path: Path | None = None
    key_path: Path | None = None
    emitter_cuit: str | None = None
    environment: Environment | None = None


def resolve_runtime_config(
    overrides: ConfigOverrides | None = None,
    *,
    _settings: Settings | None = None,
) -> Union[RuntimeConfig, ArcaError]:
    """Fusiona Settings (defaults del server) con overrides por llamada.

    Retorna RuntimeConfig si todo es válido, ArcaError en caso contrario.
    Nunca lanza excepciones — toda falla cruza la frontera MCP como Pydantic.

    Args:
        overrides: Overrides opcionales por llamada.
        _settings: Inyección de Settings para tests; si es None se crea una instancia real.

    Returns:
        RuntimeConfig validada, o ArcaError con cause estructurado.
    """
    if _settings is not None:
        settings = _settings
    else:
        # Preferir el singleton del servidor (inicializado una vez en startup).
        # Si no está inicializado (ej. llamada directa en tests), crear instancia temporal.
        try:
            from arca_mcp.config import get_server_settings
            settings = get_server_settings()
        except RuntimeError:
            settings = Settings()
    ov = overrides or ConfigOverrides()

    # --- Validar override de paths: deben ir juntos o ninguno ---
    cert_overridden = ov.cert_path is not None
    key_overridden = ov.key_path is not None
    if cert_overridden != key_overridden:
        missing = "key_path" if cert_overridden else "cert_path"
        present = "cert_path" if cert_overridden else "key_path"
        return ArcaError(
            cause=ArcaErrorCause.INVALID_CONFIG_OVERRIDE,
            message=(
                f"Override parcial de paths: se recibió '{present}' pero falta '{missing}'. "
                "cert_path y key_path deben overridearse juntos o ninguno."
            ),
        )

    # --- Resolver environment ---
    environment = ov.environment if ov.environment is not None else settings.environment

    # --- Rechazar PRODUCCION en v0.2 ---
    if environment == Environment.PRODUCCION:
        return ArcaError(
            cause=ArcaErrorCause.UNSUPPORTED_ENVIRONMENT,
            message=(
                "El ambiente 'produccion' no está soportado en v0.2. "
                "Solo 'homologacion' está habilitado hasta v1.0."
            ),
        )

    # --- Resolver cert_path ---
    if ov.cert_path is not None:
        cert_path = ov.cert_path
    elif settings.cert_path is not None:
        cert_path = settings.cert_path
    else:
        return ArcaError(
            cause=ArcaErrorCause.MISSING_CONFIG,
            message=(
                "cert_path no está configurado. "
                "Definir ARCA_CERT_PATH en el entorno o pasar cert_path como override."
            ),
        )

    # --- Resolver key_path ---
    if ov.key_path is not None:
        key_path = ov.key_path
    elif settings.key_path is not None:
        key_path = settings.key_path
    else:
        return ArcaError(
            cause=ArcaErrorCause.MISSING_CONFIG,
            message=(
                "key_path no está configurado. "
                "Definir ARCA_KEY_PATH en el entorno o pasar key_path como override."
            ),
        )

    # --- Validar que los paths existen ---
    if not cert_path.exists():
        return ArcaError(
            cause=ArcaErrorCause.MISSING_CONFIG,
            message=f"cert_path no existe en el filesystem: {cert_path}",
        )
    if not key_path.exists():
        return ArcaError(
            cause=ArcaErrorCause.MISSING_CONFIG,
            message=f"key_path no existe en el filesystem: {key_path}",
        )

    # --- Resolver emitter_cuit (opcional) ---
    emitter_cuit = ov.emitter_cuit if ov.emitter_cuit is not None else settings.cuit

    return RuntimeConfig(
        environment=environment,
        cert_path=cert_path,
        key_path=key_path,
        emitter_cuit=emitter_cuit,
    )
