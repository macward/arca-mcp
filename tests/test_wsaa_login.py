from pathlib import Path

import httpx
import pytest

from arca_mcp.errors import ArcaErrorCause
from arca_mcp.wsaa.login import validate_wsaa_login

SUCCESS_RESPONSE = """<?xml version="1.0"?>
<loginTicketResponse>
  <header>
    <uniqueId>1</uniqueId>
    <generationTime>2026-05-16T10:00:00-03:00</generationTime>
    <expirationTime>2026-05-16T22:00:00-03:00</expirationTime>
  </header>
  <credentials>
    <token>TOKEN123</token>
    <sign>SIGN456</sign>
  </credentials>
</loginTicketResponse>"""


def test_login_success(cert_key_pair, mocker):
    cert_path, key_path = cert_key_pair
    mocker.patch("arca_mcp.wsaa.login.call_login_cms", return_value=SUCCESS_RESPONSE)

    result = validate_wsaa_login(cert_path, key_path)
    assert result.ok is True
    assert result.token is not None
    assert result.token.token == "TOKEN123"
    assert result.token.sign == "SIGN456"


def test_login_invalid_cert(tmp_path, cert_key_pair):
    _, key_path = cert_key_pair
    bad_cert = tmp_path / "bad.crt"
    bad_cert.write_bytes(b"not a cert")

    result = validate_wsaa_login(bad_cert, key_path)
    assert result.ok is False
    assert result.cause == ArcaErrorCause.CERT_INVALID


def test_login_invalid_key(tmp_path, cert_key_pair):
    cert_path, _ = cert_key_pair
    bad_key = tmp_path / "bad.key"
    bad_key.write_bytes(b"not a key")

    result = validate_wsaa_login(cert_path, bad_key)
    assert result.ok is False
    assert result.cause == ArcaErrorCause.KEY_INVALID


def test_login_wsaa_unreachable(cert_key_pair, mocker):
    cert_path, key_path = cert_key_pair
    mocker.patch(
        "arca_mcp.wsaa.login.call_login_cms",
        side_effect=httpx.ConnectError("no route to host"),
    )

    result = validate_wsaa_login(cert_path, key_path)
    assert result.ok is False
    assert result.cause == ArcaErrorCause.WSAA_UNREACHABLE


def test_login_wsaa_timeout(cert_key_pair, mocker):
    cert_path, key_path = cert_key_pair
    mocker.patch(
        "arca_mcp.wsaa.login.call_login_cms",
        side_effect=httpx.TimeoutException("timed out"),
    )

    result = validate_wsaa_login(cert_path, key_path)
    assert result.ok is False
    assert result.cause == ArcaErrorCause.WSAA_UNREACHABLE


def test_login_soap_fault_unauthorized(cert_key_pair, mocker):
    cert_path, key_path = cert_key_pair
    mocker.patch(
        "arca_mcp.wsaa.login.call_login_cms",
        side_effect=ValueError("WSAA SOAP Fault: El alias no se encuentra registrado"),
    )

    result = validate_wsaa_login(cert_path, key_path)
    assert result.ok is False
    assert result.cause == ArcaErrorCause.SERVICE_UNAUTHORIZED


def test_login_generic_soap_fault(cert_key_pair, mocker):
    cert_path, key_path = cert_key_pair
    mocker.patch(
        "arca_mcp.wsaa.login.call_login_cms",
        side_effect=ValueError("WSAA SOAP Fault: error genérico"),
    )

    result = validate_wsaa_login(cert_path, key_path)
    assert result.ok is False
    assert result.cause == ArcaErrorCause.WSAA_AUTH_FAILED
