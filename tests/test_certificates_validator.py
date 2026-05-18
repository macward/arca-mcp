import datetime
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from arca_mcp.certificates import validate_certificate, validate_private_key


def _make_cert(tmp_path: Path, key, not_before, not_after) -> Path:
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .sign(key, hashes.SHA256())
    )
    path = tmp_path / "cert.crt"
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return path


def _make_key(tmp_path: Path) -> tuple[Path, rsa.RSAPrivateKey]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    path = tmp_path / "key.pem"
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    return path, key


now = datetime.datetime.now(datetime.UTC)


def test_validate_certificate_valid(tmp_path):
    _, key = _make_key(tmp_path)
    cert_path = _make_cert(tmp_path, key, now - datetime.timedelta(days=1), now + datetime.timedelta(days=365))
    result = validate_certificate(cert_path)
    assert result.valid is True
    assert result.cause is None


def test_validate_certificate_expired(tmp_path):
    _, key = _make_key(tmp_path)
    cert_path = _make_cert(tmp_path, key, now - datetime.timedelta(days=10), now - datetime.timedelta(days=1))
    result = validate_certificate(cert_path)
    assert result.valid is False
    assert result.cause == "CERT_EXPIRED"


def test_validate_certificate_not_yet_valid(tmp_path):
    _, key = _make_key(tmp_path)
    cert_path = _make_cert(tmp_path, key, now + datetime.timedelta(days=1), now + datetime.timedelta(days=365))
    result = validate_certificate(cert_path)
    assert result.valid is False
    assert result.cause == "CERT_NOT_YET_VALID"


def test_validate_certificate_invalid_file(tmp_path):
    bad = tmp_path / "bad.crt"
    bad.write_bytes(b"not a cert")
    result = validate_certificate(bad)
    assert result.valid is False
    assert result.cause == "CERT_INVALID"


def test_validate_certificate_not_found():
    result = validate_certificate(Path("/nonexistent/cert.crt"))
    assert result.valid is False
    assert result.cause == "CERT_INVALID"


def test_validate_private_key_valid(tmp_path):
    key_path, _ = _make_key(tmp_path)
    result = validate_private_key(key_path)
    assert result.valid is True
    assert result.cause is None


def test_validate_private_key_invalid(tmp_path):
    bad = tmp_path / "bad.key"
    bad.write_bytes(b"not a key")
    result = validate_private_key(bad)
    assert result.valid is False
    assert result.cause == "KEY_INVALID"


def test_validate_private_key_not_found():
    result = validate_private_key(Path("/nonexistent/key.pem"))
    assert result.valid is False
    assert result.cause == "KEY_INVALID"


def test_validate_private_key_password_protected(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    path = tmp_path / "encrypted.pem"
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.BestAvailableEncryption(b"secret123"),
        )
    )
    result = validate_private_key(path)
    assert result.valid is False
    assert result.cause == "KEY_INVALID"
    assert result.message  # mensaje legible, no crash


def test_validate_private_key_directory_path(tmp_path):
    result = validate_private_key(tmp_path)
    assert result.valid is False
    assert result.cause == "KEY_INVALID"
