import socket

from arca_mcp.certificates.errors import CertificateLoadError, PrivateKeyLoadError
from arca_mcp.error_mapping import wrap_error
from arca_mcp.errors import ArcaError, ArcaErrorCause


def test_wrap_certificate_load_error():
    err = wrap_error(CertificateLoadError("PEM corrompido"))
    assert isinstance(err, ArcaError)
    assert err.cause == ArcaErrorCause.CERT_INVALID
    assert "PEM corrompido" in err.message


def test_wrap_private_key_load_error():
    err = wrap_error(PrivateKeyLoadError("key inválida"))
    assert err.cause == ArcaErrorCause.KEY_INVALID


def test_wrap_timeout_error():
    err = wrap_error(TimeoutError("connection timed out"))
    assert err.cause == ArcaErrorCause.WSAA_UNREACHABLE


def test_wrap_connection_error():
    err = wrap_error(ConnectionError("refused"))
    assert err.cause == ArcaErrorCause.WSAA_UNREACHABLE


def test_wrap_socket_gaierror():
    err = wrap_error(socket.gaierror("name resolution failed"))
    assert err.cause == ArcaErrorCause.WSAA_UNREACHABLE


def test_wrap_unknown_exception_fallback():
    err = wrap_error(ValueError("algo raro"))
    assert err.cause == ArcaErrorCause.WSAA_AUTH_FAILED
    assert "ValueError" in err.message


def test_arca_error_cause_is_str():
    # StrEnum: los valores son strings directamente usables en JSON
    assert ArcaErrorCause.CERT_EXPIRED == "CERT_EXPIRED"
    assert str(ArcaErrorCause.CERT_KEY_MISMATCH) == "CERT_KEY_MISMATCH"
