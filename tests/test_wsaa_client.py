import pytest

from arca_mcp.wsaa.client import parse_login_ticket_response

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
