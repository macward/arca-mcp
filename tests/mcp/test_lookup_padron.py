"""Tests de las 2 tools de padrón MCP en mcp/lookup.py.

Verifica que cada tool:
  - Retorna el modelo correcto cuando el resolver, WSAA y padrón son OK.
  - Propaga ArcaError cuando resolve_runtime_config falla (MISSING_CONFIG).
  - Propaga ArcaError cuando WSAA login falla (WSAA_AUTH_FAILED).
  - Propaga ArcaError cuando el cliente padrón retorna ArcaError (PADRON_NOT_FOUND).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from arca_mcp.config.settings import Environment, Settings
from arca_mcp.errors import ArcaError, ArcaErrorCause
from arca_mcp.mcp import lookup as _lookup_mod
from arca_mcp.padron.models import FiscalAddress, PersonaDetails, TaxpayerStatus
from arca_mcp.wsaa.models import SetupCheckResult, WsaaToken


def _tool_fn(tool):
    """FastMCP may return either FunctionTool objects or plain functions."""
    return getattr(tool, "fn", tool)


get_taxpayer_details = _tool_fn(_lookup_mod.get_taxpayer_details)
validate_taxpayer_status = _tool_fn(_lookup_mod.validate_taxpayer_status)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _stub_settings(tmp_path: Path) -> Settings:
    """Crea un Settings con paths reales en disco."""
    cert_path = tmp_path / "cert.crt"
    key_path = tmp_path / "key.pem"
    cert_path.write_text("CERT")
    key_path.write_text("KEY")
    return Settings.model_construct(
        environment=Environment.HOMOLOGACION,
        cert_path=cert_path,
        key_path=key_path,
        cuit="20123456789",
    )


def _bare_settings() -> Settings:
    """Settings sin cert_path ni key_path — provoca MISSING_CONFIG."""
    return Settings.model_construct(
        environment=Environment.HOMOLOGACION,
        cert_path=None,
        key_path=None,
        cuit=None,
    )


def _ok_wsaa_result() -> SetupCheckResult:
    """Retorna un SetupCheckResult con login exitoso."""
    return SetupCheckResult(
        ok=True,
        token=WsaaToken(
            token="tok",
            sign="sig",
            generation_time="2026-01-01T00:00:00",
            expiration_time="2026-01-01T12:00:00",
        ),
    )


def _failed_wsaa_result() -> SetupCheckResult:
    """Retorna un SetupCheckResult con login fallido."""
    return SetupCheckResult(
        ok=False,
        cause=ArcaErrorCause.WSAA_AUTH_FAILED,
        message="Certificado inválido para WSAA",
    )


def _persona_activo() -> PersonaDetails:
    return PersonaDetails(
        cuit="20123456789",
        denomination="ACME S.A.",
        status="ACTIVO",
        fiscal_address=FiscalAddress(street="Corrientes", number="1234", city="Buenos Aires"),
        activities=["620100"],
    )


def _persona_inactivo() -> PersonaDetails:
    return PersonaDetails(
        cuit="20999999990",
        denomination="EX EMPRESA SRL",
        status="INACTIVO",
        fiscal_address=None,
        activities=[],
    )


def _padron_not_found_error() -> ArcaError:
    return ArcaError(
        cause=ArcaErrorCause.PADRON_NOT_FOUND,
        message="CUIT 20000000000 no encontrado en el padrón",
    )


# ---------------------------------------------------------------------------
# get_taxpayer_details — happy path
# ---------------------------------------------------------------------------

class TestGetTaxpayerDetailsHappyPath:
    """Cuando resolver, WSAA y padrón son OK, retorna PersonaDetails."""

    @pytest.mark.asyncio
    async def test_returns_persona_details(self, tmp_path):
        settings = _stub_settings(tmp_path)
        with (
            patch("arca_mcp.config.get_server_settings", return_value=settings),
            patch("arca_mcp.mcp._auth.validate_wsaa_login", new=AsyncMock(return_value=_ok_wsaa_result())),
            patch("arca_mcp.mcp.lookup.padron_client.get_persona", return_value=_persona_activo()),
        ):
            result = await get_taxpayer_details("20123456789")
        assert isinstance(result, PersonaDetails)
        assert result.cuit == "20123456789"
        assert result.denomination == "ACME S.A."
        assert result.status == "ACTIVO"

    @pytest.mark.asyncio
    async def test_passes_correct_token_sign_and_cuit(self, tmp_path):
        """La tool pasa el token/sign de WSAA y el CUIT al cliente padrón."""
        settings = _stub_settings(tmp_path)
        captured = {}

        def fake_get_persona(token, sign, emitter_cuit, query_cuit, environment):
            captured["token"] = token
            captured["sign"] = sign
            captured["emitter_cuit"] = emitter_cuit
            captured["query_cuit"] = query_cuit
            return _persona_activo()

        with (
            patch("arca_mcp.config.get_server_settings", return_value=settings),
            patch("arca_mcp.mcp._auth.validate_wsaa_login", new=AsyncMock(return_value=_ok_wsaa_result())),
            patch("arca_mcp.mcp.lookup.padron_client.get_persona", side_effect=fake_get_persona),
        ):
            await get_taxpayer_details("20123456789")

        assert captured["token"] == "tok"
        assert captured["sign"] == "sig"
        assert captured["emitter_cuit"] == "20123456789"
        assert captured["query_cuit"] == "20123456789"

    @pytest.mark.asyncio
    async def test_uses_ws_sr_padron_a4_service(self, tmp_path):
        """La tool solicita el servicio ws_sr_padron_a4 al WSAA."""
        settings = _stub_settings(tmp_path)
        captured = {}

        async def fake_validate_wsaa_login(cert_path, key_path, service, environment, cuit=None):
            captured["service"] = service
            return _ok_wsaa_result()

        with (
            patch("arca_mcp.config.get_server_settings", return_value=settings),
            patch("arca_mcp.mcp._auth.validate_wsaa_login", side_effect=fake_validate_wsaa_login),
            patch("arca_mcp.mcp.lookup.padron_client.get_persona", return_value=_persona_activo()),
        ):
            await get_taxpayer_details("20123456789")

        assert captured["service"] == "ws_sr_padron_a4"


# ---------------------------------------------------------------------------
# get_taxpayer_details — propagación de errores
# ---------------------------------------------------------------------------

class TestGetTaxpayerDetailsErrors:

    @pytest.mark.asyncio
    async def test_propagates_missing_config(self):
        with patch("arca_mcp.config.get_server_settings", return_value=_bare_settings()):
            result = await get_taxpayer_details("20123456789")
        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.MISSING_CONFIG

    @pytest.mark.asyncio
    async def test_propagates_wsaa_auth_failed(self, tmp_path):
        settings = _stub_settings(tmp_path)
        with (
            patch("arca_mcp.config.get_server_settings", return_value=settings),
            patch("arca_mcp.mcp._auth.validate_wsaa_login", new=AsyncMock(return_value=_failed_wsaa_result())),
        ):
            result = await get_taxpayer_details("20123456789")
        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.WSAA_AUTH_FAILED

    @pytest.mark.asyncio
    async def test_propagates_padron_not_found(self, tmp_path):
        settings = _stub_settings(tmp_path)
        with (
            patch("arca_mcp.config.get_server_settings", return_value=settings),
            patch("arca_mcp.mcp._auth.validate_wsaa_login", new=AsyncMock(return_value=_ok_wsaa_result())),
            patch("arca_mcp.mcp.lookup.padron_client.get_persona", return_value=_padron_not_found_error()),
        ):
            result = await get_taxpayer_details("20000000000")
        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.PADRON_NOT_FOUND


# ---------------------------------------------------------------------------
# validate_taxpayer_status — happy path
# ---------------------------------------------------------------------------

class TestValidateTaxpayerStatusHappyPath:

    @pytest.mark.asyncio
    async def test_returns_active_true_for_activo(self, tmp_path):
        settings = _stub_settings(tmp_path)
        with (
            patch("arca_mcp.config.get_server_settings", return_value=settings),
            patch("arca_mcp.mcp._auth.validate_wsaa_login", new=AsyncMock(return_value=_ok_wsaa_result())),
            patch("arca_mcp.mcp.lookup.padron_client.get_persona", return_value=_persona_activo()),
        ):
            result = await validate_taxpayer_status("20123456789")
        assert isinstance(result, TaxpayerStatus)
        assert result.cuit == "20123456789"
        assert result.active is True
        assert result.status_description == "Activo"

    @pytest.mark.asyncio
    async def test_returns_active_false_for_inactivo(self, tmp_path):
        settings = _stub_settings(tmp_path)
        with (
            patch("arca_mcp.config.get_server_settings", return_value=settings),
            patch("arca_mcp.mcp._auth.validate_wsaa_login", new=AsyncMock(return_value=_ok_wsaa_result())),
            patch("arca_mcp.mcp.lookup.padron_client.get_persona", return_value=_persona_inactivo()),
        ):
            result = await validate_taxpayer_status("20999999990")
        assert isinstance(result, TaxpayerStatus)
        assert result.cuit == "20999999990"
        assert result.active is False
        assert result.status_description == "Inactivo"

    @pytest.mark.asyncio
    async def test_returns_active_false_for_unknown_status(self, tmp_path):
        """Cualquier status distinto de ACTIVO debe resultar en active=False."""
        settings = _stub_settings(tmp_path)
        persona = PersonaDetails(
            cuit="20111111118",
            denomination="EMPRESA SUSPENDIDA SRL",
            status="SUSPENDIDO",
        )
        with (
            patch("arca_mcp.config.get_server_settings", return_value=settings),
            patch("arca_mcp.mcp._auth.validate_wsaa_login", new=AsyncMock(return_value=_ok_wsaa_result())),
            patch("arca_mcp.mcp.lookup.padron_client.get_persona", return_value=persona),
        ):
            result = await validate_taxpayer_status("20111111118")
        assert isinstance(result, TaxpayerStatus)
        assert result.active is False
        assert result.status_description == "SUSPENDIDO"


# ---------------------------------------------------------------------------
# validate_taxpayer_status — propagación de errores
# ---------------------------------------------------------------------------

class TestValidateTaxpayerStatusErrors:

    @pytest.mark.asyncio
    async def test_propagates_missing_config(self):
        with patch("arca_mcp.config.get_server_settings", return_value=_bare_settings()):
            result = await validate_taxpayer_status("20123456789")
        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.MISSING_CONFIG

    @pytest.mark.asyncio
    async def test_propagates_wsaa_auth_failed(self, tmp_path):
        settings = _stub_settings(tmp_path)
        with (
            patch("arca_mcp.config.get_server_settings", return_value=settings),
            patch("arca_mcp.mcp._auth.validate_wsaa_login", new=AsyncMock(return_value=_failed_wsaa_result())),
        ):
            result = await validate_taxpayer_status("20123456789")
        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.WSAA_AUTH_FAILED

    @pytest.mark.asyncio
    async def test_propagates_padron_not_found(self, tmp_path):
        settings = _stub_settings(tmp_path)
        with (
            patch("arca_mcp.config.get_server_settings", return_value=settings),
            patch("arca_mcp.mcp._auth.validate_wsaa_login", new=AsyncMock(return_value=_ok_wsaa_result())),
            patch("arca_mcp.mcp.lookup.padron_client.get_persona", return_value=_padron_not_found_error()),
        ):
            result = await validate_taxpayer_status("20000000000")
        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.PADRON_NOT_FOUND
