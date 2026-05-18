import httpx
import pytest

from arca_mcp.wsaa.client import call_login_cms, parse_login_ticket_response

VALID_RESPONSE = """<?xml version="1.0"?>
<loginTicketResponse>
  <header>
    <source>CN=wsaahomo</source>
    <destination>CN=test</destination>
    <uniqueId>12345</uniqueId>
    <generationTime>2026-05-16T10:00:00-03:00</generationTime>
    <expirationTime>2026-05-16T22:00:00-03:00</expirationTime>
  </header>
  <credentials>
    <token>FAKETOKEN</token>
    <sign>FAKESIGN</sign>
  </credentials>
</loginTicketResponse>"""


def test_parse_valid_response():
    token, sign, gen, exp = parse_login_ticket_response(VALID_RESPONSE)
    assert token == "FAKETOKEN"
    assert sign == "FAKESIGN"
    assert gen == "2026-05-16T10:00:00-03:00"
    assert exp == "2026-05-16T22:00:00-03:00"


def test_parse_missing_credentials():
    bad = "<loginTicketResponse><header/></loginTicketResponse>"
    with pytest.raises(ValueError, match="credentials"):
        parse_login_ticket_response(bad)


def test_parse_missing_token():
    bad = """<loginTicketResponse>
      <header>
        <generationTime>x</generationTime>
        <expirationTime>y</expirationTime>
      </header>
      <credentials><sign>S</sign></credentials>
    </loginTicketResponse>"""
    with pytest.raises(ValueError, match="incompleto"):
        parse_login_ticket_response(bad)


SOAP_OK = """<?xml version="1.0"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
  <soapenv:Body>
    <loginCmsReturn>&lt;loginTicketResponse/&gt;</loginCmsReturn>
  </soapenv:Body>
</soapenv:Envelope>"""

SOAP_FAULT = """<?xml version="1.0"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
  <soapenv:Body>
    <soapenv:Fault>
      <faultcode>soap:Server</faultcode>
      <faultstring>cert expired</faultstring>
    </soapenv:Fault>
  </soapenv:Body>
</soapenv:Envelope>"""


def _mock_transport(handler):
    return httpx.MockTransport(handler)


def test_call_login_cms_uses_client_with_tls_verify(mocker):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["content_type"] = request.headers.get("Content-Type")
        return httpx.Response(200, content=SOAP_OK)

    real_client = httpx.Client
    def fake_client(*args, **kwargs):
        captured["verify"] = kwargs.get("verify")
        kwargs["transport"] = _mock_transport(handler)
        return real_client(*args, **kwargs)

    mocker.patch("arca_mcp.wsaa.client.httpx.Client", side_effect=fake_client)

    result = call_login_cms("CMSBASE64", "https://wsaahomo.afip.gov.ar/ws/services/LoginCms")
    assert "loginTicketResponse" in result
    assert captured["verify"] is True
    assert captured["content_type"] == "text/xml; charset=utf-8"


def test_call_login_cms_retries_on_transient_error(mocker):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200, content=SOAP_OK)

    real_client = httpx.Client
    mocker.patch(
        "arca_mcp.wsaa.client.httpx.Client",
        side_effect=lambda *a, **kw: real_client(*a, **{**kw, "transport": _mock_transport(handler)}),
    )

    result = call_login_cms("CMS", "https://example/LoginCms", retries=1)
    assert "loginTicketResponse" in result
    assert calls["n"] == 2


def test_call_login_cms_raises_after_exhausting_retries(mocker):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nope", request=request)

    real_client = httpx.Client
    mocker.patch(
        "arca_mcp.wsaa.client.httpx.Client",
        side_effect=lambda *a, **kw: real_client(*a, **{**kw, "transport": _mock_transport(handler)}),
    )

    with pytest.raises(httpx.ConnectError):
        call_login_cms("CMS", "https://example/LoginCms", retries=2)


def test_call_login_cms_does_not_retry_on_soap_fault(mocker):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, content=SOAP_FAULT)

    real_client = httpx.Client
    mocker.patch(
        "arca_mcp.wsaa.client.httpx.Client",
        side_effect=lambda *a, **kw: real_client(*a, **{**kw, "transport": _mock_transport(handler)}),
    )

    with pytest.raises(ValueError, match="SOAP Fault"):
        call_login_cms("CMS", "https://example/LoginCms", retries=3)
    assert calls["n"] == 1
