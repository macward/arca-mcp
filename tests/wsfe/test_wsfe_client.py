"""Tests unitarios para arca_mcp.wsfe.client — zeep mockeado."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import zeep.exceptions

from arca_mcp.errors import ArcaError, ArcaErrorCause
from arca_mcp.wsfe.client import (
    get_aliquot_types,
    get_currency_types,
    get_voucher_types,
)
from arca_mcp.wsfe.models import CatalogItem

TOKEN = "fake-token"
SIGN = "fake-sign"
ENV = "homologacion"


def _make_item(id_: str, desc: str) -> SimpleNamespace:
    """Crea un item de catálogo simple que zeep retornaría."""
    return SimpleNamespace(Id=id_, Desc=desc)


def _make_zeep_response(items: list) -> SimpleNamespace:
    """Construye una respuesta zeep simulada con ResultGet iterable."""
    result_get = items  # list es directamente iterable
    return SimpleNamespace(ResultGet=result_get, Errors=None)


def _make_zeep_client(method_name: str, response) -> MagicMock:
    """Construye un mock de zeep.Client que retorna `response` al llamar `method_name`."""
    mock_service = MagicMock()
    getattr(mock_service, method_name).return_value = response
    mock_client = MagicMock()
    mock_client.service = mock_service
    return mock_client


# ---------------------------------------------------------------------------
# get_voucher_types
# ---------------------------------------------------------------------------

class TestGetVoucherTypes:
    def test_returns_catalog_items_on_success(self):
        """get_voucher_types convierte la respuesta de zeep en lista de CatalogItem."""
        raw_items = [_make_item("1", "Factura A"), _make_item("6", "Factura B")]
        mock_response = _make_zeep_response(raw_items)
        mock_client = _make_zeep_client("FEParamGetTiposCbte", mock_response)

        with patch("arca_mcp.wsfe.client.zeep.Client", return_value=mock_client):
            result = get_voucher_types(TOKEN, SIGN, ENV)

        assert isinstance(result, list)
        assert len(result) == 2
        assert all(isinstance(item, CatalogItem) for item in result)
        ids = [item.id for item in result]
        assert "1" in ids
        assert "6" in ids

    def test_passes_correct_auth_to_wsfe(self):
        """get_voucher_types construye Auth con Token y Sign."""
        mock_response = _make_zeep_response([])
        mock_client = _make_zeep_client("FEParamGetTiposCbte", mock_response)

        with patch("arca_mcp.wsfe.client.zeep.Client", return_value=mock_client):
            get_voucher_types(TOKEN, SIGN, ENV)

        call_kwargs = mock_client.service.FEParamGetTiposCbte.call_args
        auth = call_kwargs.kwargs.get("Auth") or call_kwargs.args[0]
        assert auth["Token"] == TOKEN
        assert auth["Sign"] == SIGN

    def test_zeep_fault_returns_arca_error(self):
        """Un zeep.exceptions.Fault retorna ArcaError con ARCA_SERVICE_ERROR."""
        fault = zeep.exceptions.Fault("Cuit no habilitado")
        mock_client = MagicMock()
        mock_client.service.FEParamGetTiposCbte.side_effect = fault

        with patch("arca_mcp.wsfe.client.zeep.Client", return_value=mock_client):
            result = get_voucher_types(TOKEN, SIGN, ENV)

        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.ARCA_SERVICE_ERROR
        assert "Fault" in result.message or "WSFEv1" in result.message

    def test_network_error_returns_arca_error(self):
        """Un error de red genérico también retorna ArcaError."""
        with patch(
            "arca_mcp.wsfe.client.zeep.Client",
            side_effect=ConnectionError("sin red"),
        ):
            result = get_voucher_types(TOKEN, SIGN, ENV)

        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.ARCA_SERVICE_ERROR

    def test_uses_homologacion_wsdl(self):
        """get_voucher_types usa el WSDL de homologación cuando environment='homologacion'."""
        captured = {}
        mock_response = _make_zeep_response([])
        mock_client = _make_zeep_client("FEParamGetTiposCbte", mock_response)

        def fake_client(wsdl):
            captured["wsdl"] = wsdl
            return mock_client

        with patch("arca_mcp.wsfe.client.zeep.Client", side_effect=fake_client):
            get_voucher_types(TOKEN, SIGN, "homologacion")

        assert "wswhomo" in captured["wsdl"]

    def test_uses_produccion_wsdl(self):
        """get_voucher_types usa el WSDL de producción cuando environment='produccion'."""
        captured = {}
        mock_response = _make_zeep_response([])
        mock_client = _make_zeep_client("FEParamGetTiposCbte", mock_response)

        def fake_client(wsdl):
            captured["wsdl"] = wsdl
            return mock_client

        with patch("arca_mcp.wsfe.client.zeep.Client", side_effect=fake_client):
            get_voucher_types(TOKEN, SIGN, "produccion")

        assert "servicios1" in captured["wsdl"]

    def test_response_with_errors_returns_arca_error(self):
        """Si la respuesta contiene Errors con Err, retorna ArcaError."""
        err_entry = SimpleNamespace(Code=99, Msg="Token inválido")
        mock_response = SimpleNamespace(
            ResultGet=None,
            Errors=SimpleNamespace(Err=[err_entry]),
        )
        mock_client = _make_zeep_client("FEParamGetTiposCbte", mock_response)

        with patch("arca_mcp.wsfe.client.zeep.Client", return_value=mock_client):
            result = get_voucher_types(TOKEN, SIGN, ENV)

        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.ARCA_SERVICE_ERROR
        assert "Token inválido" in result.message

    def test_empty_result_returns_empty_list(self):
        """ResultGet vacío retorna lista vacía."""
        mock_response = _make_zeep_response([])
        mock_client = _make_zeep_client("FEParamGetTiposCbte", mock_response)

        with patch("arca_mcp.wsfe.client.zeep.Client", return_value=mock_client):
            result = get_voucher_types(TOKEN, SIGN, ENV)

        assert result == []


# ---------------------------------------------------------------------------
# get_aliquot_types
# ---------------------------------------------------------------------------

class TestGetAliquotTypes:
    def test_returns_catalog_items_on_success(self):
        """get_aliquot_types convierte la respuesta de zeep en lista de CatalogItem."""
        raw_items = [_make_item("5", "21%"), _make_item("4", "10.5%")]
        mock_response = _make_zeep_response(raw_items)
        mock_client = _make_zeep_client("FEParamGetTiposIva", mock_response)

        with patch("arca_mcp.wsfe.client.zeep.Client", return_value=mock_client):
            result = get_aliquot_types(TOKEN, SIGN, ENV)

        assert isinstance(result, list)
        assert len(result) == 2
        assert all(isinstance(item, CatalogItem) for item in result)
        descs = [item.description for item in result]
        assert "21%" in descs
        assert "10.5%" in descs

    def test_zeep_fault_returns_arca_error(self):
        """Un zeep.exceptions.Fault en get_aliquot_types retorna ArcaError."""
        fault = zeep.exceptions.Fault("Error IVA")
        mock_client = MagicMock()
        mock_client.service.FEParamGetTiposIva.side_effect = fault

        with patch("arca_mcp.wsfe.client.zeep.Client", return_value=mock_client):
            result = get_aliquot_types(TOKEN, SIGN, ENV)

        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.ARCA_SERVICE_ERROR


# ---------------------------------------------------------------------------
# get_currency_types
# ---------------------------------------------------------------------------

class TestGetCurrencyTypes:
    def test_returns_catalog_items_on_success(self):
        """get_currency_types convierte la respuesta de zeep en lista de CatalogItem."""
        raw_items = [_make_item("PES", "Pesos Argentinos"), _make_item("DOL", "Dólar EEUU")]
        mock_response = _make_zeep_response(raw_items)
        mock_client = _make_zeep_client("FEParamGetTiposMonedas", mock_response)

        with patch("arca_mcp.wsfe.client.zeep.Client", return_value=mock_client):
            result = get_currency_types(TOKEN, SIGN, ENV)

        assert isinstance(result, list)
        assert len(result) == 2
        descriptions = [item.description for item in result]
        assert "Pesos Argentinos" in descriptions
        assert "Dólar EEUU" in descriptions

    def test_network_error_returns_arca_error(self):
        """Fallo de red en get_currency_types retorna ArcaError."""
        with patch(
            "arca_mcp.wsfe.client.zeep.Client",
            side_effect=OSError("timeout"),
        ):
            result = get_currency_types(TOKEN, SIGN, ENV)

        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.ARCA_SERVICE_ERROR
