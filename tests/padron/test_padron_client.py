"""Tests unitarios para arca_mcp.padron.client — zeep mockeado."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import zeep.exceptions

from arca_mcp.errors import ArcaError, ArcaErrorCause
from arca_mcp.padron.client import get_persona
from arca_mcp.padron.models import FiscalAddress, PersonaDetails

TOKEN = "fake-token"
SIGN = "fake-sign"
EMITTER_CUIT = "20111111112"
QUERY_CUIT = "20222222223"
ENV = "homologacion"


def _make_actividades(*codigos: str):
    """Construye el objeto actividades simulado que zeep retornaría."""
    actividad_list = [SimpleNamespace(idActividad=cod) for cod in codigos]
    return SimpleNamespace(actividad=actividad_list)


def _make_domicilio(
    direccion="Av. Corrientes",
    numero="1234",
    localidad="CABA",
    descripcionProvincia="CIUDAD AUTONOMA BUENOS AIRES",
    codPostal="C1043",
):
    """Construye el objeto domicilioFiscal simulado."""
    return SimpleNamespace(
        direccion=direccion,
        numero=numero,
        localidad=localidad,
        descripcionProvincia=descripcionProvincia,
        codPostal=codPostal,
    )


def _make_persona_juridica(
    cuit: str = QUERY_CUIT,
    razon_social: str = "ACME S.A.",
    estado: str = "ACTIVO",
    domicilio=None,
    actividades=None,
):
    """Construye un objeto persona jurídica simulado (con razonSocial)."""
    return SimpleNamespace(
        idPersona=cuit,
        razonSocial=razon_social,
        apellido=None,
        nombre=None,
        estadoClave=estado,
        domicilioFiscal=domicilio,
        actividades=actividades,
    )


def _make_persona_fisica(
    cuit: str = QUERY_CUIT,
    apellido: str = "GARCIA",
    nombre: str = "JUAN",
    estado: str = "ACTIVO",
    domicilio=None,
    actividades=None,
):
    """Construye un objeto persona física simulado (con apellido + nombre)."""
    return SimpleNamespace(
        idPersona=cuit,
        razonSocial=None,
        apellido=apellido,
        nombre=nombre,
        estadoClave=estado,
        domicilioFiscal=domicilio,
        actividades=actividades,
    )


def _make_response(persona=None, error_constancia=None):
    """Construye la respuesta completa de getPersona."""
    return SimpleNamespace(
        persona=persona,
        errorConstancia=error_constancia,
    )


def _make_zeep_client(response) -> MagicMock:
    """Construye un mock de zeep.Client que retorna `response` al llamar getPersona."""
    mock_service = MagicMock()
    mock_service.getPersona.return_value = response
    mock_client = MagicMock()
    mock_client.service = mock_service
    return mock_client


# ---------------------------------------------------------------------------
# Happy path — persona jurídica
# ---------------------------------------------------------------------------

class TestGetPersonaJuridica:
    def test_returns_persona_details_on_success(self):
        """get_persona retorna PersonaDetails para una persona jurídica válida."""
        domicilio = _make_domicilio()
        actividades = _make_actividades("620100", "620200")
        persona = _make_persona_juridica(domicilio=domicilio, actividades=actividades)
        response = _make_response(persona=persona)
        mock_client = _make_zeep_client(response)

        with patch("arca_mcp.padron.client.zeep.Client", return_value=mock_client):
            result = get_persona(TOKEN, SIGN, EMITTER_CUIT, QUERY_CUIT, ENV)

        assert isinstance(result, PersonaDetails)
        assert result.cuit == QUERY_CUIT
        assert result.denomination == "ACME S.A."
        assert result.status == "ACTIVO"

    def test_fiscal_address_is_mapped(self):
        """get_persona mapea correctamente el domicilioFiscal."""
        domicilio = _make_domicilio(
            direccion="Florida",
            numero="100",
            localidad="CABA",
            descripcionProvincia="CIUDAD AUTONOMA BUENOS AIRES",
            codPostal="C1005",
        )
        persona = _make_persona_juridica(domicilio=domicilio)
        response = _make_response(persona=persona)
        mock_client = _make_zeep_client(response)

        with patch("arca_mcp.padron.client.zeep.Client", return_value=mock_client):
            result = get_persona(TOKEN, SIGN, EMITTER_CUIT, QUERY_CUIT, ENV)

        assert isinstance(result.fiscal_address, FiscalAddress)
        assert result.fiscal_address.street == "Florida"
        assert result.fiscal_address.number == "100"
        assert result.fiscal_address.city == "CABA"
        assert result.fiscal_address.zip_code == "C1005"

    def test_activities_are_mapped(self):
        """get_persona incluye los códigos de actividad AFIP."""
        actividades = _make_actividades("620100", "620200")
        persona = _make_persona_juridica(actividades=actividades)
        response = _make_response(persona=persona)
        mock_client = _make_zeep_client(response)

        with patch("arca_mcp.padron.client.zeep.Client", return_value=mock_client):
            result = get_persona(TOKEN, SIGN, EMITTER_CUIT, QUERY_CUIT, ENV)

        assert "620100" in result.activities
        assert "620200" in result.activities

    def test_no_activities_returns_empty_list(self):
        """get_persona retorna lista vacía de actividades cuando no hay actividades."""
        persona = _make_persona_juridica(actividades=None)
        response = _make_response(persona=persona)
        mock_client = _make_zeep_client(response)

        with patch("arca_mcp.padron.client.zeep.Client", return_value=mock_client):
            result = get_persona(TOKEN, SIGN, EMITTER_CUIT, QUERY_CUIT, ENV)

        assert result.activities == []

    def test_no_domicilio_returns_none(self):
        """get_persona retorna fiscal_address=None cuando no hay domicilio."""
        persona = _make_persona_juridica(domicilio=None)
        response = _make_response(persona=persona)
        mock_client = _make_zeep_client(response)

        with patch("arca_mcp.padron.client.zeep.Client", return_value=mock_client):
            result = get_persona(TOKEN, SIGN, EMITTER_CUIT, QUERY_CUIT, ENV)

        assert result.fiscal_address is None


# ---------------------------------------------------------------------------
# Happy path — persona física
# ---------------------------------------------------------------------------

class TestGetPersonaFisica:
    def test_denomination_uses_apellido_nombre(self):
        """Para persona física, denomination usa apellido + nombre."""
        persona = _make_persona_fisica(apellido="GARCIA", nombre="JUAN")
        response = _make_response(persona=persona)
        mock_client = _make_zeep_client(response)

        with patch("arca_mcp.padron.client.zeep.Client", return_value=mock_client):
            result = get_persona(TOKEN, SIGN, EMITTER_CUIT, QUERY_CUIT, ENV)

        assert isinstance(result, PersonaDetails)
        assert "GARCIA" in result.denomination
        assert "JUAN" in result.denomination


# ---------------------------------------------------------------------------
# CUIT no encontrado
# ---------------------------------------------------------------------------

class TestCuitNotFound:
    def test_error_constancia_not_found_returns_padron_not_found(self):
        """errorConstancia con código 601 retorna ArcaError PADRON_NOT_FOUND."""
        error = SimpleNamespace(codigo="601", descripcion="El CUIT consultado no existe")
        response = _make_response(error_constancia=error)
        mock_client = _make_zeep_client(response)

        with patch("arca_mcp.padron.client.zeep.Client", return_value=mock_client):
            result = get_persona(TOKEN, SIGN, EMITTER_CUIT, QUERY_CUIT, ENV)

        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.PADRON_NOT_FOUND
        assert QUERY_CUIT in result.message

    def test_persona_none_returns_padron_not_found(self):
        """Respuesta con persona=None retorna ArcaError PADRON_NOT_FOUND."""
        response = _make_response(persona=None, error_constancia=None)
        mock_client = _make_zeep_client(response)

        with patch("arca_mcp.padron.client.zeep.Client", return_value=mock_client):
            result = get_persona(TOKEN, SIGN, EMITTER_CUIT, QUERY_CUIT, ENV)

        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.PADRON_NOT_FOUND

    def test_error_constancia_602_returns_padron_not_found(self):
        """errorConstancia con código 602 retorna ArcaError PADRON_NOT_FOUND."""
        error = SimpleNamespace(codigo="602", descripcion="Contribuyente no encontrado")
        response = _make_response(error_constancia=error)
        mock_client = _make_zeep_client(response)

        with patch("arca_mcp.padron.client.zeep.Client", return_value=mock_client):
            result = get_persona(TOKEN, SIGN, EMITTER_CUIT, QUERY_CUIT, ENV)

        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.PADRON_NOT_FOUND


# ---------------------------------------------------------------------------
# Errores de red / SOAP
# ---------------------------------------------------------------------------

class TestNetworkAndSoapErrors:
    def test_zeep_fault_returns_arca_service_error(self):
        """Un zeep.exceptions.Fault retorna ArcaError con ARCA_SERVICE_ERROR."""
        fault = zeep.exceptions.Fault("Token vencido")
        mock_client = MagicMock()
        mock_client.service.getPersona.side_effect = fault

        with patch("arca_mcp.padron.client.zeep.Client", return_value=mock_client):
            result = get_persona(TOKEN, SIGN, EMITTER_CUIT, QUERY_CUIT, ENV)

        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.ARCA_SERVICE_ERROR
        assert "Fault" in result.message or "Padrón" in result.message

    def test_network_error_returns_arca_service_error(self):
        """Un error de red genérico retorna ArcaError con ARCA_SERVICE_ERROR."""
        with patch(
            "arca_mcp.padron.client.zeep.Client",
            side_effect=ConnectionError("sin red"),
        ):
            result = get_persona(TOKEN, SIGN, EMITTER_CUIT, QUERY_CUIT, ENV)

        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.ARCA_SERVICE_ERROR

    def test_timeout_returns_arca_service_error(self):
        """Un timeout retorna ArcaError con ARCA_SERVICE_ERROR."""
        with patch(
            "arca_mcp.padron.client.zeep.Client",
            side_effect=TimeoutError("timeout"),
        ):
            result = get_persona(TOKEN, SIGN, EMITTER_CUIT, QUERY_CUIT, ENV)

        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.ARCA_SERVICE_ERROR


# ---------------------------------------------------------------------------
# WSDL según ambiente
# ---------------------------------------------------------------------------

class TestEnvironmentWsdl:
    def test_uses_homologacion_wsdl(self):
        """get_persona usa el WSDL de homologación cuando environment='homologacion'."""
        captured = {}
        persona = _make_persona_juridica()
        response = _make_response(persona=persona)

        def fake_client(wsdl):
            captured["wsdl"] = wsdl
            return _make_zeep_client(response)

        with patch("arca_mcp.padron.client.zeep.Client", side_effect=fake_client):
            get_persona(TOKEN, SIGN, EMITTER_CUIT, QUERY_CUIT, "homologacion")

        assert "awshomo" in captured["wsdl"]

    def test_uses_produccion_wsdl(self):
        """get_persona usa el WSDL de producción cuando environment='produccion'."""
        captured = {}
        persona = _make_persona_juridica()
        response = _make_response(persona=persona)

        def fake_client(wsdl):
            captured["wsdl"] = wsdl
            return _make_zeep_client(response)

        with patch("arca_mcp.padron.client.zeep.Client", side_effect=fake_client):
            get_persona(TOKEN, SIGN, EMITTER_CUIT, QUERY_CUIT, "produccion")

        assert "aws.afip.gov.ar" in captured["wsdl"]
        assert "awshomo" not in captured["wsdl"]

    def test_passes_correct_params_to_soap(self):
        """get_persona pasa token, sign, cuitRepresentada e idPersona al servicio SOAP."""
        persona = _make_persona_juridica()
        response = _make_response(persona=persona)
        mock_client = _make_zeep_client(response)

        with patch("arca_mcp.padron.client.zeep.Client", return_value=mock_client):
            get_persona(TOKEN, SIGN, EMITTER_CUIT, QUERY_CUIT, ENV)

        call_kwargs = mock_client.service.getPersona.call_args
        kwargs = call_kwargs.kwargs
        assert kwargs["token"] == TOKEN
        assert kwargs["sign"] == SIGN
        assert kwargs["cuitRepresentada"] == EMITTER_CUIT
        assert kwargs["idPersona"] == QUERY_CUIT
