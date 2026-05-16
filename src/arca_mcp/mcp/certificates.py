"""Tools MCP para validación y diagnóstico de certificados."""

from pathlib import Path

import fastmcp

from arca_mcp.certificates import (
    CertificateInspection,
    CertificateValidationResult,
)
from arca_mcp.certificates import inspect_certificate as _inspect
from arca_mcp.certificates import validate_cert_key_match as _validate_match
from arca_mcp.certificates import validate_certificate as _validate_cert
from arca_mcp.certificates import validate_private_key as _validate_key

server = fastmcp.FastMCP("certificates")


@server.tool
def validate_certificate(cert_path: str) -> CertificateValidationResult:
    """Valida un certificado X509: que sea parseable y esté vigente."""
    return _validate_cert(Path(cert_path))


@server.tool
def validate_private_key(key_path: str) -> CertificateValidationResult:
    """Valida que una private key RSA sea parseable y no esté corrupta."""
    return _validate_key(Path(key_path))


@server.tool
def validate_cert_key_match(cert_path: str, key_path: str) -> CertificateValidationResult:
    """Verifica que el certificado corresponda a la private key."""
    return _validate_match(Path(cert_path), Path(key_path))


@server.tool
def inspect_certificate(cert_path: str) -> CertificateInspection | CertificateValidationResult:
    """Retorna metadata del certificado: subject, issuer, fechas, CN, serial."""
    return _inspect(Path(cert_path))
