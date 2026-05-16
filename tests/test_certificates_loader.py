from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

from arca_mcp.certificates import CertificateLoadError, PrivateKeyLoadError, load_certificate, load_private_key


def test_load_certificate_file_not_found():
    with pytest.raises(CertificateLoadError, match="no encontrado"):
        load_certificate(Path("/nonexistent/cert.crt"))


def test_load_private_key_file_not_found():
    with pytest.raises(PrivateKeyLoadError, match="no encontrado"):
        load_private_key(Path("/nonexistent/key.pem"))


def test_load_certificate_invalid_pem(tmp_path):
    bad_cert = tmp_path / "bad.crt"
    bad_cert.write_bytes(b"esto no es un certificado")
    with pytest.raises(CertificateLoadError, match="inválido"):
        load_certificate(bad_cert)


def test_load_private_key_invalid_pem(tmp_path):
    bad_key = tmp_path / "bad.key"
    bad_key.write_bytes(b"esto no es una key")
    with pytest.raises(PrivateKeyLoadError, match="inválida"):
        load_private_key(bad_key)


def test_load_certificate_returns_x509(tmp_path):
    # Certificado de prueba autofirmado generado con cryptography
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    import datetime

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.UTC))
        .not_valid_after(datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=365))
        .sign(key, hashes.SHA256())
    )
    cert_path = tmp_path / "cert.crt"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))

    result = load_certificate(cert_path)
    assert isinstance(result, x509.Certificate)


def test_load_private_key_returns_rsa(tmp_path):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_path = tmp_path / "key.pem"
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )

    result = load_private_key(key_path)
    assert isinstance(result, RSAPrivateKey)
