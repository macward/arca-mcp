from pathlib import Path

from arca_mcp.errors import ArcaErrorCause
from arca_mcp.wsaa.doctor import run_setup_doctor

SUCCESS_RESPONSE = """<?xml version="1.0"?>
<loginTicketResponse>
  <header>
    <uniqueId>1</uniqueId>
    <generationTime>2026-05-16T10:00:00-03:00</generationTime>
    <expirationTime>2026-05-16T22:00:00-03:00</expirationTime>
  </header>
  <credentials>
    <token>TOK</token>
    <sign>SIG</sign>
  </credentials>
</loginTicketResponse>"""


def test_all_ok(cert_key_pair, mocker):
    cert_path, key_path = cert_key_pair
    mocker.patch("arca_mcp.wsaa.login.call_login_cms", return_value=SUCCESS_RESPONSE)

    report = run_setup_doctor(cert_path, key_path)

    assert report.all_ok is True
    assert report.failed_check is None
    assert len(report.checks) == 5
    assert [c.name for c in report.checks] == [
        "private_key",
        "certificate",
        "cert_key_match",
        "wsaa_login",
        "service_authorization",
    ]
    assert all(c.ok for c in report.checks)
    assert not any(c.skipped for c in report.checks)


def test_private_key_fails_short_circuits(cert_key_pair, tmp_path):
    cert_path, _ = cert_key_pair
    bad_key = tmp_path / "bad.key"
    bad_key.write_bytes(b"not a key")

    report = run_setup_doctor(cert_path, bad_key)

    assert report.all_ok is False
    assert report.failed_check == "private_key"
    assert report.checks[0].ok is False
    assert report.checks[0].cause == ArcaErrorCause.KEY_INVALID
    # Todos los downstream skipped
    assert all(c.skipped for c in report.checks[1:])


def test_certificate_fails_short_circuits(cert_key_pair, tmp_path):
    _, key_path = cert_key_pair
    bad_cert = tmp_path / "bad.crt"
    bad_cert.write_bytes(b"not a cert")

    report = run_setup_doctor(bad_cert, key_path)

    assert report.all_ok is False
    assert report.failed_check == "certificate"
    assert report.checks[0].ok is True  # key fine
    assert report.checks[1].ok is False  # cert bad
    assert report.checks[1].cause == ArcaErrorCause.CERT_INVALID
    # Solo se ejecutaron 2 checks, los otros 3 son skipped
    assert sum(1 for c in report.checks if c.skipped) == 3


def test_cert_key_mismatch_short_circuits(tmp_path, mocker):
    # Genero dos pares distintos y uso cert de uno con key de otro
    import datetime as dt
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    def make_pair(suffix):
        k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subj = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"t{suffix}")])
        now = dt.datetime.now(dt.UTC)
        c = (x509.CertificateBuilder()
             .subject_name(subj).issuer_name(subj)
             .public_key(k.public_key()).serial_number(1)
             .not_valid_before(now - dt.timedelta(days=1))
             .not_valid_after(now + dt.timedelta(days=365))
             .sign(k, hashes.SHA256()))
        cp = tmp_path / f"c{suffix}.crt"
        kp = tmp_path / f"k{suffix}.pem"
        cp.write_bytes(c.public_bytes(serialization.Encoding.PEM))
        kp.write_bytes(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
        return cp, kp

    cert_a, _ = make_pair("a")
    _, key_b = make_pair("b")

    report = run_setup_doctor(cert_a, key_b)

    assert report.all_ok is False
    assert report.failed_check == "cert_key_match"
    assert report.checks[2].cause == ArcaErrorCause.CERT_KEY_MISMATCH
    assert report.checks[3].skipped is True
    assert report.checks[4].skipped is True


def test_wsaa_login_fails_short_circuits(cert_key_pair, mocker):
    import httpx
    cert_path, key_path = cert_key_pair
    mocker.patch(
        "arca_mcp.wsaa.login.call_login_cms",
        side_effect=httpx.ConnectError("unreachable"),
    )

    report = run_setup_doctor(cert_path, key_path)

    assert report.all_ok is False
    assert report.failed_check == "wsaa_login"
    # Los 3 primeros pasaron
    assert all(c.ok for c in report.checks[:3])
    # wsaa_login falló
    assert report.checks[3].ok is False
    assert report.checks[3].cause == ArcaErrorCause.WSAA_UNREACHABLE
    # service_authorization skipped
    assert report.checks[4].skipped is True


def test_report_has_5_checks_always(cert_key_pair, mocker):
    """Independientemente de dónde falle, el reporte siempre debe tener 5 checks."""
    cert_path, key_path = cert_key_pair
    mocker.patch("arca_mcp.wsaa.login.call_login_cms", return_value=SUCCESS_RESPONSE)
    report = run_setup_doctor(cert_path, key_path)
    assert len(report.checks) == 5
