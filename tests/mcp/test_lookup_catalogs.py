"""Tests de las 5 catalog tools MCP en mcp/lookup.py.

Verifica que cada tool:
  - Retorna lista de CatalogItem cuando el resolver y el cliente WSFEv1 son OK.
  - Propaga ArcaError cuando resolve_runtime_config falla.
  - Propaga ArcaError cuando WSAA login falla.
  - Propaga ArcaError cuando el cliente WSFEv1 retorna ArcaError.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from arca_mcp.config_settings import Environment, Settings
from arca_mcp.errors import ArcaError, ArcaErrorCause
from arca_mcp.mcp import lookup as _lookup_mod
from arca_mcp.wsaa.models import SetupCheckResult, WsaaToken
from arca_mcp.wsfe.models import CatalogItem


def _tool_fn(tool):
    """FastMCP may return either FunctionTool objects or plain functions."""
    return getattr(tool, "fn", tool)


get_voucher_types = _tool_fn(_lookup_mod.get_voucher_types)
get_document_types = _tool_fn(_lookup_mod.get_document_types)
get_tax_types = _tool_fn(_lookup_mod.get_tax_types)
get_aliquot_types = _tool_fn(_lookup_mod.get_aliquot_types)
get_currency_types = _tool_fn(_lookup_mod.get_currency_types)


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


def _catalog_items() -> list[CatalogItem]:
    return [CatalogItem(id="1", description="Item 1"), CatalogItem(id="2", description="Item 2")]


# ---------------------------------------------------------------------------
# Propagación de ArcaError desde resolve_runtime_config
# ---------------------------------------------------------------------------

class TestResolverErrorPropagation:
    """Cuando resolve_runtime_config retorna ArcaError, las tools lo propagan directamente."""

    def _bare_settings(self):
        return Settings.model_construct(
            environment=Environment.HOMOLOGACION,
            cert_path=None,
            key_path=None,
            cuit=None,
        )

    @pytest.mark.asyncio
    async def test_get_voucher_types_propagates_missing_config(self):
        with patch("arca_mcp.config.get_server_settings", return_value=self._bare_settings()):
            result = await get_voucher_types()
        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.MISSING_CONFIG

    @pytest.mark.asyncio
    async def test_get_document_types_propagates_missing_config(self):
        with patch("arca_mcp.config.get_server_settings", return_value=self._bare_settings()):
            result = await get_document_types()
        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.MISSING_CONFIG

    @pytest.mark.asyncio
    async def test_get_tax_types_propagates_missing_config(self):
        with patch("arca_mcp.config.get_server_settings", return_value=self._bare_settings()):
            result = await get_tax_types()
        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.MISSING_CONFIG

    @pytest.mark.asyncio
    async def test_get_aliquot_types_propagates_missing_config(self):
        with patch("arca_mcp.config.get_server_settings", return_value=self._bare_settings()):
            result = await get_aliquot_types()
        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.MISSING_CONFIG

    @pytest.mark.asyncio
    async def test_get_currency_types_propagates_missing_config(self):
        with patch("arca_mcp.config.get_server_settings", return_value=self._bare_settings()):
            result = await get_currency_types()
        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.MISSING_CONFIG


# ---------------------------------------------------------------------------
# Propagación de ArcaError desde WSAA login
# ---------------------------------------------------------------------------

class TestWsaaLoginErrorPropagation:
    """Cuando WSAA login falla, las tools retornan ArcaError WSAA_AUTH_FAILED."""

    @pytest.mark.asyncio
    async def test_get_voucher_types_propagates_wsaa_failure(self, tmp_path):
        settings = _stub_settings(tmp_path)
        with (
            patch("arca_mcp.config.get_server_settings", return_value=settings),
            patch("arca_mcp.mcp._auth.validate_wsaa_login", new=AsyncMock(return_value=_failed_wsaa_result())),
        ):
            result = await get_voucher_types()
        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.WSAA_AUTH_FAILED

    @pytest.mark.asyncio
    async def test_get_document_types_propagates_wsaa_failure(self, tmp_path):
        settings = _stub_settings(tmp_path)
        with (
            patch("arca_mcp.config.get_server_settings", return_value=settings),
            patch("arca_mcp.mcp._auth.validate_wsaa_login", new=AsyncMock(return_value=_failed_wsaa_result())),
        ):
            result = await get_document_types()
        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.WSAA_AUTH_FAILED


# ---------------------------------------------------------------------------
# Propagación de ArcaError desde el cliente WSFEv1
# ---------------------------------------------------------------------------

class TestWsfeClientErrorPropagation:
    """Cuando wsfe_client retorna ArcaError, la tool lo propaga directamente."""

    def _wsfe_error(self) -> ArcaError:
        return ArcaError(
            cause=ArcaErrorCause.ARCA_SERVICE_ERROR,
            message="WSFEv1 SOAP Fault",
        )

    @pytest.mark.asyncio
    async def test_get_voucher_types_propagates_wsfe_error(self, tmp_path):
        settings = _stub_settings(tmp_path)
        with (
            patch("arca_mcp.config.get_server_settings", return_value=settings),
            patch("arca_mcp.mcp._auth.validate_wsaa_login", new=AsyncMock(return_value=_ok_wsaa_result())),
            patch("arca_mcp.mcp.lookup.wsfe_client.get_voucher_types", return_value=self._wsfe_error()),
        ):
            result = await get_voucher_types()
        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.ARCA_SERVICE_ERROR

    @pytest.mark.asyncio
    async def test_get_currency_types_propagates_wsfe_error(self, tmp_path):
        settings = _stub_settings(tmp_path)
        with (
            patch("arca_mcp.config.get_server_settings", return_value=settings),
            patch("arca_mcp.mcp._auth.validate_wsaa_login", new=AsyncMock(return_value=_ok_wsaa_result())),
            patch("arca_mcp.mcp.lookup.wsfe_client.get_currency_types", return_value=self._wsfe_error()),
        ):
            result = await get_currency_types()
        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.ARCA_SERVICE_ERROR


# ---------------------------------------------------------------------------
# Happy path: tool retorna lista de CatalogItem
# ---------------------------------------------------------------------------

class TestHappyPath:
    """Cuando resolver y clientes OK, las tools retornan lista de CatalogItem."""

    @pytest.mark.asyncio
    async def test_get_voucher_types_returns_catalog_items(self, tmp_path):
        settings = _stub_settings(tmp_path)
        items = _catalog_items()
        with (
            patch("arca_mcp.config.get_server_settings", return_value=settings),
            patch("arca_mcp.mcp._auth.validate_wsaa_login", new=AsyncMock(return_value=_ok_wsaa_result())),
            patch("arca_mcp.mcp.lookup.wsfe_client.get_voucher_types", return_value=items),
        ):
            result = await get_voucher_types()
        assert isinstance(result, list)
        assert len(result) == 2
        assert all(isinstance(item, CatalogItem) for item in result)

    @pytest.mark.asyncio
    async def test_get_document_types_returns_catalog_items(self, tmp_path):
        settings = _stub_settings(tmp_path)
        items = _catalog_items()
        with (
            patch("arca_mcp.config.get_server_settings", return_value=settings),
            patch("arca_mcp.mcp._auth.validate_wsaa_login", new=AsyncMock(return_value=_ok_wsaa_result())),
            patch("arca_mcp.mcp.lookup.wsfe_client.get_document_types", return_value=items),
        ):
            result = await get_document_types()
        assert isinstance(result, list)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_tax_types_returns_catalog_items(self, tmp_path):
        settings = _stub_settings(tmp_path)
        items = _catalog_items()
        with (
            patch("arca_mcp.config.get_server_settings", return_value=settings),
            patch("arca_mcp.mcp._auth.validate_wsaa_login", new=AsyncMock(return_value=_ok_wsaa_result())),
            patch("arca_mcp.mcp.lookup.wsfe_client.get_tax_types", return_value=items),
        ):
            result = await get_tax_types()
        assert isinstance(result, list)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_aliquot_types_returns_catalog_items(self, tmp_path):
        settings = _stub_settings(tmp_path)
        items = _catalog_items()
        with (
            patch("arca_mcp.config.get_server_settings", return_value=settings),
            patch("arca_mcp.mcp._auth.validate_wsaa_login", new=AsyncMock(return_value=_ok_wsaa_result())),
            patch("arca_mcp.mcp.lookup.wsfe_client.get_aliquot_types", return_value=items),
        ):
            result = await get_aliquot_types()
        assert isinstance(result, list)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_currency_types_returns_catalog_items(self, tmp_path):
        settings = _stub_settings(tmp_path)
        items = _catalog_items()
        with (
            patch("arca_mcp.config.get_server_settings", return_value=settings),
            patch("arca_mcp.mcp._auth.validate_wsaa_login", new=AsyncMock(return_value=_ok_wsaa_result())),
            patch("arca_mcp.mcp.lookup.wsfe_client.get_currency_types", return_value=items),
        ):
            result = await get_currency_types()
        assert isinstance(result, list)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_voucher_types_passes_correct_token_and_sign(self, tmp_path):
        """La tool pasa el token y sign obtenidos de WSAA al cliente WSFEv1."""
        settings = _stub_settings(tmp_path)
        captured = {}

        def fake_get_voucher_types(token, sign, environment, cuit):
            captured["token"] = token
            captured["sign"] = sign
            captured["environment"] = environment
            captured["cuit"] = cuit
            return _catalog_items()

        with (
            patch("arca_mcp.config.get_server_settings", return_value=settings),
            patch("arca_mcp.mcp._auth.validate_wsaa_login", new=AsyncMock(return_value=_ok_wsaa_result())),
            patch("arca_mcp.mcp.lookup.wsfe_client.get_voucher_types", side_effect=fake_get_voucher_types),
        ):
            await get_voucher_types()

        assert captured["token"] == "tok"
        assert captured["sign"] == "sig"
        assert captured["environment"] == "homologacion"
        assert captured["cuit"] == "20123456789"

    @pytest.mark.asyncio
    async def test_get_voucher_types_returns_empty_list_when_no_items(self, tmp_path):
        """Lista vacía es un resultado válido."""
        settings = _stub_settings(tmp_path)
        with (
            patch("arca_mcp.config.get_server_settings", return_value=settings),
            patch("arca_mcp.mcp._auth.validate_wsaa_login", new=AsyncMock(return_value=_ok_wsaa_result())),
            patch("arca_mcp.mcp.lookup.wsfe_client.get_voucher_types", return_value=[]),
        ):
            result = await get_voucher_types()
        assert result == []
