"""End-to-end tests for the generate_invoice_pdf MCP tool."""

import base64
import io

import pytest
from pypdf import PdfReader

from arca_mcp.mcp import invoicing as _inv_mod

_tool_fn = lambda tool: getattr(tool, "fn", tool)  # noqa: E731
generate_invoice_pdf_tool = _tool_fn(_inv_mod.generate_invoice_pdf_tool)

VALID_VOUCHER_PARAMS = dict(
    cbte_tipo=1,
    punto_venta=1,
    cbte_nro=42,
    fecha_cbte="20240115",
    cae="12345678901234",
    cae_fch_vto="20240215",
    imp_neto="1000.00",
    alicuota_id="5",
    cuit_emisor="20123456789",
    emisor_razon_social="ACME S.A.",
    emisor_domicilio="Av. Siempre Viva 742",
    cuit_receptor="20987654321",
    doc_tipo=80,
)


@pytest.mark.asyncio
async def test_valid_input_returns_pdf_b64_and_filename():
    result = await generate_invoice_pdf_tool(**VALID_VOUCHER_PARAMS)
    assert "pdf_b64" in result
    assert "filename" in result
    assert result["filename"] == "factura_1_00001_00000042.pdf"


@pytest.mark.asyncio
async def test_pdf_decodable_and_valid():
    result = await generate_invoice_pdf_tool(**VALID_VOUCHER_PARAMS)
    pdf_bytes = base64.b64decode(result["pdf_b64"])
    assert pdf_bytes[:4] == b"%PDF"


@pytest.mark.asyncio
async def test_pdf_contains_cae():
    result = await generate_invoice_pdf_tool(**VALID_VOUCHER_PARAMS)
    pdf_bytes = base64.b64decode(result["pdf_b64"])
    reader = PdfReader(io.BytesIO(pdf_bytes))
    text = "".join(page.extract_text() or "" for page in reader.pages)
    assert "12345678901234" in text


@pytest.mark.asyncio
async def test_invalid_imp_neto_returns_error():
    params = {**VALID_VOUCHER_PARAMS, "imp_neto": "not_a_number"}
    result = await generate_invoice_pdf_tool(**params)
    assert "error" in result
    assert result["error"]["cause"] == "INVALID_CATALOG_VALUE"


@pytest.mark.asyncio
async def test_invalid_cae_returns_error():
    params = {**VALID_VOUCHER_PARAMS, "cae": "badcae"}
    result = await generate_invoice_pdf_tool(**params)
    assert "error" in result
    assert result["error"]["cause"] == "INVALID_CATALOG_VALUE"


@pytest.mark.asyncio
async def test_consumidor_final_doc_tipo_99_succeeds_without_nro_doc():
    params = {**VALID_VOUCHER_PARAMS, "doc_tipo": 99}
    result = await generate_invoice_pdf_tool(**params)
    assert "pdf_b64" in result


@pytest.mark.asyncio
async def test_doc_tipo_96_requires_nro_doc_receptor():
    params = {**VALID_VOUCHER_PARAMS, "doc_tipo": 96}
    result = await generate_invoice_pdf_tool(**params)
    assert "error" in result
    assert result["error"]["cause"] == "INVALID_CATALOG_VALUE"


@pytest.mark.asyncio
async def test_doc_tipo_96_with_explicit_nro_doc_receptor_succeeds():
    params = {**VALID_VOUCHER_PARAMS, "doc_tipo": 96, "nro_doc_receptor": "12345678"}
    result = await generate_invoice_pdf_tool(**params)
    assert "pdf_b64" in result
