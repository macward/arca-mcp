"""Tests para las funciones puras de validación de catálogos AFIP."""

from __future__ import annotations

import pytest

from arca_mcp.validation.catalogs import (
    is_valid_currency,
    is_valid_invoice_type,
    is_valid_vat_condition,
)


class TestIsValidInvoiceType:
    """Tests para is_valid_invoice_type."""

    @pytest.mark.parametrize("invoice_type", [
        "1",   # Factura A
        "2",   # Nota de Débito A
        "3",   # Nota de Crédito A
        "6",   # Factura B
        "7",   # Nota de Débito B
        "8",   # Nota de Crédito B
        "11",  # Factura C
        "12",  # Nota de Débito C
        "13",  # Nota de Crédito C
        "51",  # Factura M
        "52",  # Nota de Débito M
        "53",  # Nota de Crédito M
    ])
    def test_valid_invoice_types_return_true(self, invoice_type: str):
        assert is_valid_invoice_type(invoice_type) is True

    @pytest.mark.parametrize("invoice_type", [
        "0",
        "4",
        "5",
        "99",
        "100",
        "",
        "A",
        "factura",
    ])
    def test_invalid_invoice_types_return_false(self, invoice_type: str):
        assert is_valid_invoice_type(invoice_type) is False

    def test_case_sensitive_uppercase_invalid(self):
        # Códigos son strings numéricos; valores no numéricos son inválidos
        assert is_valid_invoice_type("1 ") is False  # trailing space
        assert is_valid_invoice_type(" 1") is False  # leading space


class TestIsValidVatCondition:
    """Tests para is_valid_vat_condition."""

    @pytest.mark.parametrize("vat_condition", [
        "1",   # IVA Responsable Inscripto
        "2",   # IVA Responsable No Inscripto
        "3",   # IVA No Responsable
        "4",   # IVA Sujeto Exento
        "5",   # Consumidor Final
        "6",   # Responsable Monotributo
        "7",   # Sujeto No Categorizado
        "8",   # Importador del Exterior
        "9",   # Cliente del Exterior
        "10",  # IVA Liberado – Ley Nº 19.640
        "13",  # Monotributista Social
        "16",  # IVA No Alcanzado
    ])
    def test_valid_vat_conditions_return_true(self, vat_condition: str):
        assert is_valid_vat_condition(vat_condition) is True

    @pytest.mark.parametrize("vat_condition", [
        "0",
        "11",
        "12",
        "14",
        "15",
        "99",
        "",
        "RI",
        "responsable",
    ])
    def test_invalid_vat_conditions_return_false(self, vat_condition: str):
        assert is_valid_vat_condition(vat_condition) is False

    def test_case_sensitive_with_whitespace(self):
        assert is_valid_vat_condition(" 1") is False
        assert is_valid_vat_condition("1 ") is False


class TestIsValidCurrency:
    """Tests para is_valid_currency."""

    @pytest.mark.parametrize("currency", [
        "PES",  # Pesos Argentinos
        "DOL",  # Dólar Estadounidense
        "EUR",  # Euro
        "BRL",  # Real Brasileño
        "012",  # Dólar Libre EEUU
    ])
    def test_valid_currencies_return_true(self, currency: str):
        assert is_valid_currency(currency) is True

    @pytest.mark.parametrize("currency", [
        "USD",
        "ARS",
        "GBP",
        "pes",
        "dol",
        "eur",
        "Pes",
        "",
        "PESO",
        "DOLAR",
    ])
    def test_invalid_currencies_return_false(self, currency: str):
        assert is_valid_currency(currency) is False

    def test_case_sensitive_lowercase_invalid(self):
        assert is_valid_currency("pes") is False
        assert is_valid_currency("Pes") is False
        assert is_valid_currency("PEs") is False
