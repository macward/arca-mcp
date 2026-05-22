"""Tests for ConfirmedVoucherInput model and generate_invoice_pdf."""

import pytest
from pydantic import ValidationError

from arca_mcp.invoicing.pdf import ConfirmedVoucherInput, generate_invoice_pdf

VALID_VOUCHER = dict(
    cbte_tipo=1,
    punto_venta=1,
    cbte_nro=1,
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

PDF_MAGIC = b"%PDF"
MIN_PDF_SIZE = 5000  # bytes


def test_valid_voucher_construction():
    v = ConfirmedVoucherInput(**VALID_VOUCHER)
    assert v.cae == "12345678901234"
    assert v.moneda == "PES"
    assert v.ctz == 1.0


def test_doc_tipo_80_auto_derives_nro_doc_receptor():
    v = ConfirmedVoucherInput(**VALID_VOUCHER)
    assert v.nro_doc_receptor == v.cuit_receptor


def test_doc_tipo_99_auto_derives_nro_doc_receptor_zero():
    v = ConfirmedVoucherInput(**{**VALID_VOUCHER, "doc_tipo": 99})
    assert v.nro_doc_receptor == "0"


def test_explicit_nro_doc_receptor_overrides_auto_derivation():
    v = ConfirmedVoucherInput(**{**VALID_VOUCHER, "nro_doc_receptor": "12345678"})
    assert v.nro_doc_receptor == "12345678"


def test_doc_tipo_96_requires_explicit_nro_doc_receptor():
    with pytest.raises(ValidationError, match="nro_doc_receptor is required"):
        ConfirmedVoucherInput(**{**VALID_VOUCHER, "doc_tipo": 96})


def test_doc_tipo_96_with_explicit_nro_doc_receptor():
    v = ConfirmedVoucherInput(**{**VALID_VOUCHER, "doc_tipo": 96, "nro_doc_receptor": "12345678"})
    assert v.nro_doc_receptor == "12345678"


def test_invalid_cae_raises():
    with pytest.raises(ValidationError):
        ConfirmedVoucherInput(**{**VALID_VOUCHER, "cae": "1234"})


def test_invalid_alicuota_raises():
    with pytest.raises(ValidationError):
        ConfirmedVoucherInput(**{**VALID_VOUCHER, "alicuota_id": "99"})


def test_imp_iva_and_total_computed():
    from decimal import Decimal

    v = ConfirmedVoucherInput(**VALID_VOUCHER)
    # alicuota_id "5" = 21%
    assert v.imp_iva == (v.imp_neto * Decimal("0.21")).quantize(Decimal("0.01"))
    assert v.imp_total == v.imp_neto + v.imp_iva


def test_generate_invoice_pdf_returns_pdf_bytes():
    v = ConfirmedVoucherInput(**VALID_VOUCHER)
    result = generate_invoice_pdf(v)
    assert isinstance(result, bytes)
    assert result[:4] == PDF_MAGIC


def test_generate_invoice_pdf_contains_cae():
    import io

    from pypdf import PdfReader

    v = ConfirmedVoucherInput(**VALID_VOUCHER)
    result = generate_invoice_pdf(v)
    reader = PdfReader(io.BytesIO(result))
    text = "".join(page.extract_text() or "" for page in reader.pages)
    assert "12345678901234" in text


def test_generate_invoice_pdf_has_qr_embedded():
    v = ConfirmedVoucherInput(**VALID_VOUCHER)
    result = generate_invoice_pdf(v)
    # ReportLab encodes the image as an XObject — the marker always appears
    assert b"/Subtype /Image" in result
