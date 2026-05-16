from lxml import etree

from arca_mcp.wsaa.tra import build_tra


def test_build_tra_returns_bytes():
    tra = build_tra("wsfe")
    assert isinstance(tra, bytes)


def test_build_tra_is_valid_xml():
    tra = build_tra("wsfe")
    root = etree.fromstring(tra)
    assert root.tag == "loginTicketRequest"
    assert root.get("version") == "1.0"


def test_build_tra_has_service():
    tra = build_tra("wsfe")
    root = etree.fromstring(tra)
    assert root.findtext("service") == "wsfe"


def test_build_tra_has_unique_id():
    tra = build_tra("wsfe")
    root = etree.fromstring(tra)
    unique_id = root.findtext("header/uniqueId")
    assert unique_id and unique_id.isdigit()


def test_build_tra_generation_before_expiration():
    tra = build_tra("wsfe", ttl_seconds=3600)
    root = etree.fromstring(tra)
    gen = root.findtext("header/generationTime")
    exp = root.findtext("header/expirationTime")
    assert gen < exp


def test_build_tra_different_unique_ids():
    a = build_tra("wsfe")
    b = build_tra("wsfe")
    root_a = etree.fromstring(a)
    root_b = etree.fromstring(b)
    assert root_a.findtext("header/uniqueId") != root_b.findtext("header/uniqueId")
