import socket

from arca_mcp.certificates.errors import CertificateLoadError, PrivateKeyLoadError
from arca_mcp.errors import ArcaError, ArcaErrorCause


def wrap_error(exc: Exception) -> ArcaError:
    """Mapea excepciones conocidas a ArcaError estructurado."""
    msg = str(exc)

    if isinstance(exc, CertificateLoadError):
        return ArcaError(cause=ArcaErrorCause.CERT_INVALID, message=msg)

    if isinstance(exc, PrivateKeyLoadError):
        return ArcaError(cause=ArcaErrorCause.KEY_INVALID, message=msg)

    if isinstance(exc, (TimeoutError, ConnectionError, socket.gaierror)):
        return ArcaError(cause=ArcaErrorCause.WSAA_UNREACHABLE, message=f"No se pudo conectar a WSAA: {msg}")

    return ArcaError(cause=ArcaErrorCause.WSAA_AUTH_FAILED, message=f"{type(exc).__name__}: {msg}")
