"""Tools MCP para validación y diagnóstico de certificados."""

from __future__ import annotations

import fastmcp

from arca_mcp.certificates import (
    CertificateInspection,
    CertificateValidationResult,
)
from arca_mcp.certificates import inspect_certificate as _inspect
from arca_mcp.certificates import validate_cert_key_match as _validate_match
from arca_mcp.certificates import validate_certificate as _validate_cert
from arca_mcp.certificates import validate_private_key as _validate_key
from arca_mcp.config import ConfigOverrides, resolve_runtime_config
from arca_mcp.config_settings import Environment
from arca_mcp.errors import ArcaError

server = fastmcp.FastMCP("certificates")


def _build_overrides(
    cert_path: str | None,
    key_path: str | None,
    environment: str | None,
) -> ConfigOverrides:
    """Construye ConfigOverrides a partir de strings opcionales."""
    from pathlib import Path

    env: Environment | None = None
    if environment is not None:
        env = Environment(environment)
    return ConfigOverrides(
        cert_path=Path(cert_path) if cert_path is not None else None,
        key_path=Path(key_path) if key_path is not None else None,
        environment=env,
    )


@server.tool
def validate_certificate(
    cert_path: str | None = None,
    key_path: str | None = None,
) -> CertificateValidationResult | ArcaError:
    """Valida un certificado X509: que sea parseable y esté vigente.

    `cert_path` y `key_path` son overrides opcionales. Si no se pasan, el
    resolver los toma de Settings (ARCA_CERT_PATH / ARCA_KEY_PATH). Deben
    pasarse juntos o ninguno.
    """
    config = resolve_runtime_config(_build_overrides(cert_path, key_path, None))
    if isinstance(config, ArcaError):
        return config
    return _validate_cert(config.cert_path)


@server.tool
def validate_private_key(
    cert_path: str | None = None,
    key_path: str | None = None,
) -> CertificateValidationResult | ArcaError:
    """Valida que una private key RSA sea parseable y no esté corrupta.

    `cert_path` y `key_path` son overrides opcionales. Si no se pasan, el
    resolver los toma de Settings (ARCA_CERT_PATH / ARCA_KEY_PATH). Deben
    pasarse juntos o ninguno.
    """
    config = resolve_runtime_config(_build_overrides(cert_path, key_path, None))
    if isinstance(config, ArcaError):
        return config
    return _validate_key(config.key_path)


@server.tool
def validate_cert_key_match(
    cert_path: str | None = None,
    key_path: str | None = None,
) -> CertificateValidationResult | ArcaError:
    """Verifica que el certificado corresponda a la private key.

    `cert_path` y `key_path` son overrides opcionales. Si no se pasan, el
    resolver los toma de Settings (ARCA_CERT_PATH / ARCA_KEY_PATH). Deben
    pasarse juntos o ninguno.
    """
    config = resolve_runtime_config(_build_overrides(cert_path, key_path, None))
    if isinstance(config, ArcaError):
        return config
    return _validate_match(config.cert_path, config.key_path)


@server.tool
def inspect_certificate(
    cert_path: str | None = None,
    key_path: str | None = None,
) -> CertificateInspection | CertificateValidationResult | ArcaError:
    """Retorna metadata del certificado: subject, issuer, fechas, CN, serial.

    `cert_path` y `key_path` son overrides opcionales. Si no se pasan, el
    resolver los toma de Settings (ARCA_CERT_PATH / ARCA_KEY_PATH). Deben
    pasarse juntos o ninguno.
    """
    config = resolve_runtime_config(_build_overrides(cert_path, key_path, None))
    if isinstance(config, ArcaError):
        return config
    return _inspect(config.cert_path)
