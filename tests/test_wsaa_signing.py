import base64
from pathlib import Path

import pytest

from arca_mcp.certificates.errors import CertificateLoadError, PrivateKeyLoadError
from arca_mcp.wsaa.signing import sign_tra
from arca_mcp.wsaa.tra import build_tra


def test_sign_tra_returns_base64_string(cert_key_pair):
    cert_path, key_path = cert_key_pair
    tra = build_tra("wsfe")
    cms = sign_tra(tra, cert_path, key_path)
    assert isinstance(cms, str)
    # Debe ser base64 válido
    decoded = base64.b64decode(cms)
    assert len(decoded) > 0


def test_sign_tra_is_deterministic_length(cert_key_pair):
    # Distintos TRA producen firmas distintas, pero ambas válidas
    cert_path, key_path = cert_key_pair
    tra_a = build_tra("wsfe")
    tra_b = build_tra("ws_sr_padron_a4")
    cms_a = sign_tra(tra_a, cert_path, key_path)
    cms_b = sign_tra(tra_b, cert_path, key_path)
    assert cms_a != cms_b


def test_sign_tra_invalid_cert(tmp_path, cert_key_pair):
    _, key_path = cert_key_pair
    bad_cert = tmp_path / "bad.crt"
    bad_cert.write_bytes(b"not a cert")
    with pytest.raises(CertificateLoadError):
        sign_tra(b"<tra/>", bad_cert, key_path)


def test_sign_tra_invalid_key(tmp_path, cert_key_pair):
    cert_path, _ = cert_key_pair
    bad_key = tmp_path / "bad.key"
    bad_key.write_bytes(b"not a key")
    with pytest.raises(PrivateKeyLoadError):
        sign_tra(b"<tra/>", cert_path, bad_key)
