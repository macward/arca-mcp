"""Tests para las 3 validation tools MCP en mcp/lookup.py.

Estas tools son validaciones puras (sin red, sin cert, sin WSAA):
  - validate_invoice_type
  - validate_vat_condition
  - validate_currency
"""

from __future__ import annotations

import pytest

from arca_mcp.mcp import lookup as _lookup_mod

# FastMCP wraps functions in FunctionTool objects; access .fn to call them directly.
validate_invoice_type = _lookup_mod.validate_invoice_type.fn
validate_vat_condition = _lookup_mod.validate_vat_condition.fn
validate_currency = _lookup_mod.validate_currency.fn


class TestValidateInvoiceType:
    """Tests para la tool validate_invoice_type."""

    def test_valid_factura_a_returns_true(self):
        result = validate_invoice_type("1")
        assert result == {"invoice_type": "1", "valid": True}

    def test_valid_factura_b_returns_true(self):
        result = validate_invoice_type("6")
        assert result == {"invoice_type": "6", "valid": True}

    def test_valid_factura_c_returns_true(self):
        result = validate_invoice_type("11")
        assert result == {"invoice_type": "11", "valid": True}

    def test_valid_factura_m_returns_true(self):
        result = validate_invoice_type("51")
        assert result == {"invoice_type": "51", "valid": True}

    def test_invalid_type_returns_false(self):
        result = validate_invoice_type("99")
        assert result == {"invoice_type": "99", "valid": False}

    def test_empty_string_returns_false(self):
        result = validate_invoice_type("")
        assert result == {"invoice_type": "", "valid": False}

    def test_unknown_string_returns_false(self):
        result = validate_invoice_type("factura")
        assert result == {"invoice_type": "factura", "valid": False}

    @pytest.mark.parametrize("invoice_type", ["1", "2", "3", "6", "7", "8", "11", "12", "13", "51", "52", "53"])
    def test_all_valid_types_return_true(self, invoice_type: str):
        result = validate_invoice_type(invoice_type)
        assert result["valid"] is True
        assert result["invoice_type"] == invoice_type


class TestValidateVatCondition:
    """Tests para la tool validate_vat_condition."""

    def test_valid_responsable_inscripto_returns_true(self):
        result = validate_vat_condition("1")
        assert result == {"vat_condition": "1", "valid": True}

    def test_valid_consumidor_final_returns_true(self):
        result = validate_vat_condition("5")
        assert result == {"vat_condition": "5", "valid": True}

    def test_valid_monotributo_returns_true(self):
        result = validate_vat_condition("6")
        assert result == {"vat_condition": "6", "valid": True}

    def test_invalid_condition_returns_false(self):
        result = validate_vat_condition("99")
        assert result == {"vat_condition": "99", "valid": False}

    def test_empty_string_returns_false(self):
        result = validate_vat_condition("")
        assert result == {"vat_condition": "", "valid": False}

    def test_unknown_string_returns_false(self):
        result = validate_vat_condition("RI")
        assert result == {"vat_condition": "RI", "valid": False}

    @pytest.mark.parametrize("vat_condition", ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "13", "16"])
    def test_all_valid_conditions_return_true(self, vat_condition: str):
        result = validate_vat_condition(vat_condition)
        assert result["valid"] is True
        assert result["vat_condition"] == vat_condition


class TestValidateCurrency:
    """Tests para la tool validate_currency."""

    def test_valid_pesos_returns_true(self):
        result = validate_currency("PES")
        assert result == {"currency": "PES", "valid": True}

    def test_valid_dolar_returns_true(self):
        result = validate_currency("DOL")
        assert result == {"currency": "DOL", "valid": True}

    def test_valid_euro_returns_true(self):
        result = validate_currency("EUR")
        assert result == {"currency": "EUR", "valid": True}

    def test_valid_dolar_libre_returns_true(self):
        result = validate_currency("012")
        assert result == {"currency": "012", "valid": True}

    def test_invalid_usd_returns_false(self):
        result = validate_currency("USD")
        assert result == {"currency": "USD", "valid": False}

    def test_lowercase_pes_returns_false(self):
        result = validate_currency("pes")
        assert result == {"currency": "pes", "valid": False}

    def test_empty_string_returns_false(self):
        result = validate_currency("")
        assert result == {"currency": "", "valid": False}

    @pytest.mark.parametrize("currency", ["PES", "DOL", "EUR", "BRL", "012"])
    def test_all_valid_currencies_return_true(self, currency: str):
        result = validate_currency(currency)
        assert result["valid"] is True
        assert result["currency"] == currency
