"""Configuración central para arca-mcp.

Re-exporta Environment y Settings (antes en config.py) para compatibilidad
con imports existentes, más las nuevas exportaciones del resolver central.

Exports:
    Environment            — enum de ambientes (HOMOLOGACION, PRODUCCION)
    Settings               — defaults del servidor vía variables de entorno ARCA_*
    RuntimeConfig          — estructura validada e inmutable por llamada MCP
    ConfigOverrides        — overrides opcionales por llamada
    resolve_runtime_config — resolver central que fusiona Settings + overrides
    init_server_settings   — inicializa el singleton de Settings al arrancar el servidor
    get_server_settings    — retorna el singleton de Settings (inicializado en startup)

Regla de diseño: las tools MCP NO leen env vars directamente. Solo Settings y
el resolver lo hacen. El singleton se inicializa una única vez en server.py y
se pasa al resolver vía _settings.
"""

from arca_mcp.config.settings import Environment, Settings
from arca_mcp.config.resolver import ConfigOverrides, RuntimeConfig, resolve_runtime_config

# Singleton de Settings cargado al startup del servidor.
# Nunca accedido directamente por las tools — solo consumido por el resolver.
_server_settings: Settings | None = None


def init_server_settings(settings: Settings | None = None) -> Settings:
    """Inicializa el singleton de Settings al arrancar el servidor.

    Si se pasa un objeto Settings explícito (útil en tests), lo usa directamente.
    Si no, crea una instancia real leyendo ARCA_* env vars y archivo .env.

    Idempotente: si ya fue inicializado, lo reemplaza (permite reinit en tests).
    """
    global _server_settings
    _server_settings = settings if settings is not None else Settings()
    return _server_settings


def get_server_settings() -> Settings:
    """Retorna el singleton de Settings.

    Raises:
        RuntimeError: si init_server_settings() no fue llamado antes.
    """
    if _server_settings is None:
        raise RuntimeError(
            "Settings del servidor no inicializados. "
            "Llamar init_server_settings() al arrancar el servidor."
        )
    return _server_settings


__all__ = [
    "Environment",
    "Settings",
    "RuntimeConfig",
    "ConfigOverrides",
    "resolve_runtime_config",
    "init_server_settings",
    "get_server_settings",
]
