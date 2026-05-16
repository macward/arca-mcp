import datetime
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from arca_mcp.certificates import CertificateInspection, CertificateValidationResult, inspect_certificate

now = datetime.datetime.now(datetime.UTC)


def _make_cert(tmp_path: Path, cn: str = "REINGART MARIANO JOSE", org: str = "AFIP") -> Path:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, cn),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, org),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(12345)
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=365))
        .sign(key, hashes.SHA256())
    )
    path = tmp_path / "cert.crt"
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return path


def test_inspect_returns_inspection_model(tmp_path):
    path = _make_cert(tmp_path)
    result = inspect_certificate(path)
    assert isinstance(result, CertificateInspection)


def test_inspect_common_name(tmp_path):
    path = _make_cert(tmp_path, cn="REINGART MARIANO JOSE")
    result = inspect_certificate(path)
    assert result.common_name == "REINGART MARIANO JOSE"


def test_inspect_organization(tmp_path):
    path = _make_cert(tmp_path, org="AFIP")
    result = inspect_certificate(path)
    assert result.organization == "AFIP"


def test_inspect_serial_number(tmp_path):
    path = _make_cert(tmp_path)
    result = inspect_certificate(path)
    assert result.serial_number == "12345"


def test_inspect_is_self_signed(tmp_path):
    path = _make_cert(tmp_path)
    result = inspect_certificate(path)
    assert result.is_self_signed is True


def test_inspect_dates_are_iso(tmp_path):
    path = _make_cert(tmp_path)
    result = inspect_certificate(path)
    # Deben ser strings ISO parseables
    from datetime import datetime
    datetime.fromisoformat(result.not_valid_before)
    datetime.fromisoformat(result.not_valid_after)


def test_inspect_invalid_cert(tmp_path):
    bad = tmp_path / "bad.crt"
    bad.write_bytes(b"not a cert")
    result = inspect_certificate(bad)
    assert isinstance(result, CertificateValidationResult)
    assert result.valid is False
    assert result.cause == "CERT_INVALID"
