"""Integration tests for the generate_qr MCP tool."""

import base64

import pytest

from arca_mcp.mcp import invoicing as _inv_mod

_tool_fn = lambda tool: getattr(tool, "fn", tool)  # noqa: E731
generate_qr = _tool_fn(_inv_mod.generate_qr)

VALID_QR_PARAMS = dict(
    fecha="2024-01-15",
    cuit="20123456789",
    ptoVta=1,
    tipoCmp=1,
    nroCmp=1,
    importe=1210.00,
    moneda="PES",
    ctz=1.0,
    tipoDocRec=80,
    nroDocRec="20987654321",
    codAut="12345678901234",
)


@pytest.mark.asyncio
async def test_valid_input_returns_qr_url_and_png_b64():
    result = await generate_qr(**VALID_QR_PARAMS)
    assert "qr_url" in result
    assert "qr_png_b64" in result
    assert result["qr_url"].startswith("https://www.arca.gob.ar/fe/qr/?p=")
    assert len(result["qr_png_b64"]) > 0


@pytest.mark.asyncio
async def test_qr_png_b64_is_valid_base64_png():
    result = await generate_qr(**VALID_QR_PARAMS)
    png_bytes = base64.b64decode(result["qr_png_b64"])
    assert png_bytes[:4] == b"\x89PNG"


@pytest.mark.asyncio
async def test_invalid_cae_13_digits_returns_invalid_cae():
    params = {**VALID_QR_PARAMS, "codAut": "1234567890123"}  # 13 digits
    result = await generate_qr(**params)
    assert "error" in result
    assert result["error"]["cause"] == "INVALID_CAE"
