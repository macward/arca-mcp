from arca_mcp.errors import ArcaErrorCause
from arca_mcp.wsaa import ArcaService, validate_service_authorization

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


def test_service_authorized(cert_key_pair, mocker):
    cert_path, key_path = cert_key_pair
    mocker.patch("arca_mcp.wsaa.login.call_login_cms", return_value=SUCCESS_RESPONSE)

    result = validate_service_authorization(cert_path, key_path, "wsfe")
    assert result.ok is True
    assert result.token is not None


def test_service_unauthorized_alias_fault(cert_key_pair, mocker):
    cert_path, key_path = cert_key_pair
    mocker.patch(
        "arca_mcp.wsaa.login.call_login_cms",
        side_effect=ValueError("WSAA SOAP Fault: El alias no se encuentra registrado en los padrones"),
    )

    result = validate_service_authorization(cert_path, key_path, "wsfe")
    assert result.ok is False
    assert result.cause == ArcaErrorCause.SERVICE_UNAUTHORIZED


def test_empty_service_rejected(cert_key_pair):
    cert_path, key_path = cert_key_pair

    result = validate_service_authorization(cert_path, key_path, "")
    assert result.ok is False
    assert result.cause == ArcaErrorCause.SERVICE_UNAUTHORIZED
    assert "vacío" in result.message


def test_whitespace_service_rejected(cert_key_pair):
    cert_path, key_path = cert_key_pair
    result = validate_service_authorization(cert_path, key_path, "   ")
    assert result.ok is False
    assert result.cause == ArcaErrorCause.SERVICE_UNAUTHORIZED


def test_arca_service_enum_can_be_used(cert_key_pair, mocker):
    cert_path, key_path = cert_key_pair
    mocker.patch("arca_mcp.wsaa.login.call_login_cms", return_value=SUCCESS_RESPONSE)

    # El enum es un StrEnum, debe funcionar como string al pasarlo
    result = validate_service_authorization(cert_path, key_path, ArcaService.WS_SR_PADRON_A4)
    assert result.ok is True


def test_arbitrary_service_string_accepted(cert_key_pair, mocker):
    """No debe haber whitelist rígida — cualquier string no vacío es válido a priori,
    la decisión la toma WSAA."""
    cert_path, key_path = cert_key_pair
    mocker.patch("arca_mcp.wsaa.login.call_login_cms", return_value=SUCCESS_RESPONSE)

    result = validate_service_authorization(cert_path, key_path, "ws_servicio_nuevo_2027")
    assert result.ok is True
