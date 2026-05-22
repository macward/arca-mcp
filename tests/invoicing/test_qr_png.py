"""Tests for generate_qr_png."""

from arca_mcp.invoicing.qr import QRPayload, build_qr_url, generate_qr_png

VALID_PAYLOAD = dict(
    fecha="2024-01-15",
    cuit="20123456789",
    ptoVta=1,
    tipoCmp=1,
    nroCmp=1,
    importe=1000.00,
    moneda="PES",
    ctz=1.0,
    tipoDocRec=80,
    nroDocRec="20987654321",
    codAut="12345678901234",
)

PNG_MAGIC = b"\x89PNG"


def test_generate_qr_png_returns_non_empty_bytes():
    payload = QRPayload(**VALID_PAYLOAD)
    result = generate_qr_png(payload)
    assert isinstance(result, bytes)
    assert len(result) > 0


def test_generate_qr_png_is_valid_png():
    payload = QRPayload(**VALID_PAYLOAD)
    result = generate_qr_png(payload)
    assert result[:4] == PNG_MAGIC


def test_build_qr_url_contains_arca_domain():
    payload = QRPayload(**VALID_PAYLOAD)
    url = build_qr_url(payload)
    assert isinstance(url, str)
    assert "arca.gob.ar/fe/qr" in url
