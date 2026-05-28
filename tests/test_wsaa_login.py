import datetime

import httpx
import pytest

from arca_mcp.errors import ArcaErrorCause
from arca_mcp.wsaa import token_store
from arca_mcp.wsaa.login import validate_wsaa_login
from arca_mcp.wsaa.models import WsaaToken
from arca_mcp.wsaa.wsaa_cache import WsaaCache

SUCCESS_RESPONSE = """<?xml version="1.0"?>
<loginTicketResponse>
  <header>
    <uniqueId>1</uniqueId>
    <generationTime>2026-05-16T10:00:00-03:00</generationTime>
    <expirationTime>2099-05-16T22:00:00-03:00</expirationTime>
  </header>
  <credentials>
    <token>TOKEN123</token>
    <sign>SIGN456</sign>
  </credentials>
</loginTicketResponse>"""


@pytest.fixture(autouse=True)
def clean_token_store():
    token_store.clear_store()
    yield
    token_store.clear_store()


@pytest.mark.asyncio
async def test_login_success(cert_key_pair, mocker):
    cert_path, key_path = cert_key_pair
    mocker.patch("arca_mcp.wsaa.login.call_login_cms", return_value=SUCCESS_RESPONSE)

    result = await validate_wsaa_login(cert_path, key_path)
    assert result.ok is True
    assert result.token is not None
    assert result.token.token == "TOKEN123"
    assert result.token.sign == "SIGN456"


@pytest.mark.asyncio
async def test_login_uses_cached_token(cert_key_pair, mocker):
    cert_path, key_path = cert_key_pair
    call_login = mocker.patch(
        "arca_mcp.wsaa.login.call_login_cms",
        return_value=SUCCESS_RESPONSE,
    )

    first = await validate_wsaa_login(cert_path, key_path, service="wsfe")
    second = await validate_wsaa_login(cert_path, key_path, service="wsfe")

    assert first.ok is True
    assert second.ok is True
    assert second.token is not None
    assert second.token.token == "TOKEN123"
    assert call_login.call_count == 1


@pytest.mark.asyncio
async def test_login_invalid_cert(tmp_path, cert_key_pair):
    _, key_path = cert_key_pair
    bad_cert = tmp_path / "bad.crt"
    bad_cert.write_bytes(b"not a cert")

    result = await validate_wsaa_login(bad_cert, key_path)
    assert result.ok is False
    assert result.cause == ArcaErrorCause.CERT_INVALID


@pytest.mark.asyncio
async def test_login_invalid_key(tmp_path, cert_key_pair):
    cert_path, _ = cert_key_pair
    bad_key = tmp_path / "bad.key"
    bad_key.write_bytes(b"not a key")

    result = await validate_wsaa_login(cert_path, bad_key)
    assert result.ok is False
    assert result.cause == ArcaErrorCause.KEY_INVALID


@pytest.mark.asyncio
async def test_login_wsaa_unreachable(cert_key_pair, mocker):
    cert_path, key_path = cert_key_pair
    mocker.patch(
        "arca_mcp.wsaa.login.call_login_cms",
        side_effect=httpx.ConnectError("no route to host"),
    )

    result = await validate_wsaa_login(cert_path, key_path)
    assert result.ok is False
    assert result.cause == ArcaErrorCause.WSAA_UNREACHABLE


@pytest.mark.asyncio
async def test_login_wsaa_timeout(cert_key_pair, mocker):
    cert_path, key_path = cert_key_pair
    mocker.patch(
        "arca_mcp.wsaa.login.call_login_cms",
        side_effect=httpx.TimeoutException("timed out"),
    )

    result = await validate_wsaa_login(cert_path, key_path)
    assert result.ok is False
    assert result.cause == ArcaErrorCause.WSAA_UNREACHABLE


@pytest.mark.asyncio
async def test_login_soap_fault_unauthorized(cert_key_pair, mocker):
    cert_path, key_path = cert_key_pair
    mocker.patch(
        "arca_mcp.wsaa.login.call_login_cms",
        side_effect=ValueError("WSAA SOAP Fault: El alias no se encuentra registrado"),
    )

    result = await validate_wsaa_login(cert_path, key_path)
    assert result.ok is False
    assert result.cause == ArcaErrorCause.SERVICE_UNAUTHORIZED


@pytest.mark.asyncio
async def test_login_generic_soap_fault(cert_key_pair, mocker):
    cert_path, key_path = cert_key_pair
    mocker.patch(
        "arca_mcp.wsaa.login.call_login_cms",
        side_effect=ValueError("WSAA SOAP Fault: error genérico"),
    )

    result = await validate_wsaa_login(cert_path, key_path)
    assert result.ok is False
    assert result.cause == ArcaErrorCause.WSAA_AUTH_FAILED


@pytest.mark.asyncio
async def test_login_ta_already_valid_returns_error_cause(cert_key_pair, mocker):
    """WSAA rechaza re-emitir TA mientras uno está vivo → ok=False, causa dedicada."""
    cert_path, key_path = cert_key_pair
    mocker.patch(
        "arca_mcp.wsaa.login.call_login_cms",
        side_effect=ValueError(
            "WSAA SOAP Fault: El CEE ya posee un TA valido para el acceso al WSN solicitado"
        ),
    )

    result = await validate_wsaa_login(cert_path, key_path, service="wsfe")
    assert result.ok is False
    assert result.cause is not None
    assert result.cause.value == "WSAA_TA_ALREADY_VALID"
    assert result.token is None
    assert result.message is not None and "cuit" in result.message.lower()


@pytest.mark.asyncio
async def test_filesystem_cache_expired_token_triggers_relogin(cert_key_pair, mocker, tmp_path):
    """Token vencido en disco al arrancar → re-login transparente y persiste el nuevo token."""
    cert_path, key_path = cert_key_pair
    cuit = "20123456789"

    expired_token = WsaaToken(
        token="old-token",
        sign="old-sign",
        generation_time="2020-01-01T00:00:00+00:00",
        expiration_time="2020-01-01T12:00:00+00:00",
    )
    fs_cache = WsaaCache(cache_dir=tmp_path / "tokens")
    fs_cache.save(cuit, expired_token)

    call_login = mocker.patch(
        "arca_mcp.wsaa.login.call_login_cms",
        return_value=SUCCESS_RESPONSE,
    )

    result = await validate_wsaa_login(cert_path, key_path, cuit=cuit, cache=fs_cache)

    assert result.ok is True
    assert result.token is not None
    assert result.token.token == "TOKEN123"
    assert call_login.call_count == 1

    refreshed = fs_cache.get(cuit)
    assert refreshed is not None
    assert refreshed.token == "TOKEN123"


@pytest.mark.asyncio
async def test_filesystem_cache_near_expiry_triggers_relogin(cert_key_pair, mocker, tmp_path):
    """Token expiring in < 10 min → proactive refresh even if not yet expired."""
    cert_path, key_path = cert_key_pair
    cuit = "20123456789"
    now = datetime.datetime.now(datetime.timezone.utc)

    fs_cache = WsaaCache(
        cache_dir=tmp_path / "tokens",
        _now=lambda: now,
    )
    near_expiry_token = WsaaToken(
        token="almost-expired-token",
        sign="s",
        generation_time=now.isoformat(),
        expiration_time=(now + datetime.timedelta(minutes=9)).isoformat(),
    )
    fs_cache.save(cuit, near_expiry_token)

    call_login = mocker.patch(
        "arca_mcp.wsaa.login.call_login_cms",
        return_value=SUCCESS_RESPONSE,
    )

    result = await validate_wsaa_login(cert_path, key_path, cuit=cuit, cache=fs_cache)

    assert result.ok is True
    assert result.token is not None
    assert result.token.token == "TOKEN123"
    assert call_login.call_count == 1


# --- Guard: empty token or sign must return ok=False ---

@pytest.mark.asyncio
async def test_empty_token_returns_ok_false(cert_key_pair, mocker):
    """parse_login_ticket_response retorna token vacío → ok=False, no falso positivo."""
    cert_path, key_path = cert_key_pair
    mocker.patch("arca_mcp.wsaa.login.call_login_cms", return_value="<irrelevant/>")
    mocker.patch(
        "arca_mcp.wsaa.login.parse_login_ticket_response",
        return_value=("", "SIGN456", "2026-01-01T00:00:00+00:00", "2099-01-01T00:00:00+00:00"),
    )

    result = await validate_wsaa_login(cert_path, key_path)
    assert result.ok is False
    assert result.token is None
    assert result.cause == ArcaErrorCause.WSAA_AUTH_FAILED


@pytest.mark.asyncio
async def test_empty_sign_returns_ok_false(cert_key_pair, mocker):
    """parse_login_ticket_response retorna firma vacía → ok=False, no falso positivo."""
    cert_path, key_path = cert_key_pair
    mocker.patch("arca_mcp.wsaa.login.call_login_cms", return_value="<irrelevant/>")
    mocker.patch(
        "arca_mcp.wsaa.login.parse_login_ticket_response",
        return_value=("TOKEN123", "", "2026-01-01T00:00:00+00:00", "2099-01-01T00:00:00+00:00"),
    )

    result = await validate_wsaa_login(cert_path, key_path)
    assert result.ok is False
    assert result.token is None
    assert result.cause == ArcaErrorCause.WSAA_AUTH_FAILED


@pytest.mark.asyncio
async def test_valid_token_and_sign_returns_ok_true(cert_key_pair, mocker):
    """Token y firma presentes y no vacíos → ok=True."""
    cert_path, key_path = cert_key_pair
    mocker.patch("arca_mcp.wsaa.login.call_login_cms", return_value=SUCCESS_RESPONSE)

    result = await validate_wsaa_login(cert_path, key_path)
    assert result.ok is True
    assert result.token is not None
    assert result.token.token == "TOKEN123"
    assert result.token.sign == "SIGN456"
