"""Configuración central para arca-mcp.

Re-exporta Environment y Settings (antes en config.py) para compatibilidad
con imports existentes, más las nuevas exportaciones del resolver central.

Exports:
    Environment        — enum de ambientes (HOMOLOGACION, PRODUCCION)
    Settings           — defaults del servidor vía variables de entorno ARCA_*
    RuntimeConfig      — estructura validada e inmutable por llamada MCP
    ConfigOverrides    — overrides opcionales por llamada
    resolve_runtime_config — resolver central que fusiona Settings + overrides
"""

from arca_mcp.config_settings import Environment, Settings
from arca_mcp.config.resolver import ConfigOverrides, RuntimeConfig, resolve_runtime_config

__all__ = [
    "Environment",
    "Settings",
    "RuntimeConfig",
    "ConfigOverrides",
    "resolve_runtime_config",
]
