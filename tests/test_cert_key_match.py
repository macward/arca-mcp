import datetime
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from arca_mcp.certificates import validate_cert_key_match

now = datetime.datetime.now(datetime.UTC)


def _make_pair(tmp_path: Path, suffix: str = "") -> tuple[Path, Path]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=365))
        .sign(key, hashes.SHA256())
    )

    cert_path = tmp_path / f"cert{suffix}.crt"
    key_path = tmp_path / f"key{suffix}.pem"

    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    return cert_path, key_path


def test_matching_cert_and_key(tmp_path):
    cert_path, key_path = _make_pair(tmp_path)
    result = validate_cert_key_match(cert_path, key_path)
    assert result.valid is True
    assert result.cause is None


def test_mismatched_cert_and_key(tmp_path):
    cert_path, _ = _make_pair(tmp_path, suffix="1")
    _, key_path = _make_pair(tmp_path, suffix="2")
    result = validate_cert_key_match(cert_path, key_path)
    assert result.valid is False
    assert result.cause == "CERT_KEY_MISMATCH"


def test_invalid_cert(tmp_path):
    _, key_path = _make_pair(tmp_path)
    bad_cert = tmp_path / "bad.crt"
    bad_cert.write_bytes(b"not a cert")
    result = validate_cert_key_match(bad_cert, key_path)
    assert result.valid is False
    assert result.cause == "CERT_INVALID"


def test_invalid_key(tmp_path):
    cert_path, _ = _make_pair(tmp_path)
    bad_key = tmp_path / "bad.key"
    bad_key.write_bytes(b"not a key")
    result = validate_cert_key_match(cert_path, bad_key)
    assert result.valid is False
    assert result.cause == "KEY_INVALID"
