"""Tests de integración resolver → tools MCP.

Verifica que las 7 tools MCP propagan correctamente los errores del resolver
(MISSING_CONFIG, INVALID_CONFIG_OVERRIDE, UNSUPPORTED_ENVIRONMENT) y que, cuando
el resolver resuelve ok, delegan a las capas internas con los paths correctos.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from arca_mcp.errors import ArcaError, ArcaErrorCause
from arca_mcp.mcp import certificates as _certs_mod
from arca_mcp.mcp import setup as _setup_mod


def _tool_fn(tool):
    """FastMCP may return either FunctionTool objects or plain functions."""
    return getattr(tool, "fn", tool)


validate_certificate = _tool_fn(_certs_mod.validate_certificate)
validate_private_key = _tool_fn(_certs_mod.validate_private_key)
validate_cert_key_match = _tool_fn(_certs_mod.validate_cert_key_match)
inspect_certificate = _tool_fn(_certs_mod.inspect_certificate)
validate_wsaa_login = _tool_fn(_setup_mod.validate_wsaa_login)
validate_service_authorization = _tool_fn(_setup_mod.validate_service_authorization)
setup_doctor = _tool_fn(_setup_mod.setup_doctor)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _stub_settings(tmp_path: Path, *, cert: bool = True, key: bool = True):
    """Crea un Settings stub con paths reales en disco."""
    from arca_mcp.config.settings import Environment, Settings

    cert_path = tmp_path / "cert.crt"
    key_path = tmp_path / "key.pem"
    if cert:
        cert_path.write_text("CERT")
    if key:
        key_path.write_text("KEY")
    return Settings.model_construct(
        environment=Environment.HOMOLOGACION,
        cert_path=cert_path if cert else None,
        key_path=key_path if key else None,
        cuit=None,
    )


# ---------------------------------------------------------------------------
# MISSING_CONFIG propagado desde resolver hacia cada tool
# ---------------------------------------------------------------------------

class TestMissingConfigPropagation:
    """Cuando Settings no tiene paths, las tools deben retornar ArcaError MISSING_CONFIG."""

    def _bare_settings(self):
        from arca_mcp.config.settings import Environment, Settings
        return Settings.model_construct(
            environment=Environment.HOMOLOGACION,
            cert_path=None,
            key_path=None,
            cuit=None,
        )

    def test_validate_certificate_missing_config(self):
        with patch("arca_mcp.config.get_server_settings", return_value=self._bare_settings()):
            result = validate_certificate()
        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.MISSING_CONFIG

    def test_validate_private_key_missing_config(self):
        with patch("arca_mcp.config.get_server_settings", return_value=self._bare_settings()):
            result = validate_private_key()
        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.MISSING_CONFIG

    def test_validate_cert_key_match_missing_config(self):
        with patch("arca_mcp.config.get_server_settings", return_value=self._bare_settings()):
            result = validate_cert_key_match()
        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.MISSING_CONFIG

    def test_inspect_certificate_missing_config(self):
        with patch("arca_mcp.config.get_server_settings", return_value=self._bare_settings()):
            result = inspect_certificate()
        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.MISSING_CONFIG

    @pytest.mark.asyncio
    async def test_validate_wsaa_login_missing_config(self):
        with patch("arca_mcp.config.get_server_settings", return_value=self._bare_settings()):
            result = await validate_wsaa_login()
        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.MISSING_CONFIG

    @pytest.mark.asyncio
    async def test_validate_service_authorization_missing_config(self):
        with patch("arca_mcp.config.get_server_settings", return_value=self._bare_settings()):
            result = await validate_service_authorization()
        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.MISSING_CONFIG

    @pytest.mark.asyncio
    async def test_setup_doctor_missing_config(self):
        with patch("arca_mcp.config.get_server_settings", return_value=self._bare_settings()):
            result = await setup_doctor()
        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.MISSING_CONFIG


# ---------------------------------------------------------------------------
# INVALID_CONFIG_OVERRIDE: pasar solo cert_path o solo key_path
# ---------------------------------------------------------------------------

class TestInvalidConfigOverridePropagation:
    def test_validate_certificate_only_cert_path(self, tmp_path):
        cert_path = tmp_path / "cert.crt"
        cert_path.write_text("CERT")
        result = validate_certificate(cert_path=str(cert_path))
        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.INVALID_CONFIG_OVERRIDE

    @pytest.mark.asyncio
    async def test_setup_doctor_only_key_path(self, tmp_path):
        key_path = tmp_path / "key.pem"
        key_path.write_text("KEY")
        result = await setup_doctor(key_path=str(key_path))
        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.INVALID_CONFIG_OVERRIDE


# ---------------------------------------------------------------------------
# UNSUPPORTED_ENVIRONMENT
# ---------------------------------------------------------------------------

class TestUnsupportedEnvironmentPropagation:
    @pytest.mark.asyncio
    async def test_validate_wsaa_login_produccion(self, tmp_path):
        cert_path = tmp_path / "cert.crt"
        key_path = tmp_path / "key.pem"
        cert_path.write_text("CERT")
        key_path.write_text("KEY")
        result = await validate_wsaa_login(
            cert_path=str(cert_path),
            key_path=str(key_path),
            environment="produccion",
        )
        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.UNSUPPORTED_ENVIRONMENT

    @pytest.mark.asyncio
    async def test_setup_doctor_produccion(self, tmp_path):
        cert_path = tmp_path / "cert.crt"
        key_path = tmp_path / "key.pem"
        cert_path.write_text("CERT")
        key_path.write_text("KEY")
        result = await setup_doctor(
            cert_path=str(cert_path),
            key_path=str(key_path),
            environment="produccion",
        )
        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.UNSUPPORTED_ENVIRONMENT


# ---------------------------------------------------------------------------
# Happy path: overrides resuelven a paths correctos
# ---------------------------------------------------------------------------

class TestOverridesResolveToCorrectPaths:
    def test_validate_certificate_uses_override_path(self, cert_key_pair):
        """Con override, validate_certificate llama a la capa interna con el path correcto."""
        cert_path, key_path = cert_key_pair
        result = validate_certificate(cert_path=str(cert_path), key_path=str(key_path))
        assert not isinstance(result, ArcaError)
        assert result.valid is True

    def test_validate_private_key_uses_override_path(self, cert_key_pair):
        cert_path, key_path = cert_key_pair
        result = validate_private_key(cert_path=str(cert_path), key_path=str(key_path))
        assert not isinstance(result, ArcaError)
        assert result.valid is True

    def test_validate_cert_key_match_uses_override_paths(self, cert_key_pair):
        cert_path, key_path = cert_key_pair
        result = validate_cert_key_match(cert_path=str(cert_path), key_path=str(key_path))
        assert not isinstance(result, ArcaError)
        assert result.valid is True

    def test_inspect_certificate_uses_override_path(self, cert_key_pair):
        from arca_mcp.certificates import CertificateInspection
        cert_path, key_path = cert_key_pair
        result = inspect_certificate(cert_path=str(cert_path), key_path=str(key_path))
        assert not isinstance(result, ArcaError)
        assert isinstance(result, CertificateInspection)

    def test_settings_defaults_used_when_no_override(self, tmp_path):
        """Sin overrides, las tools usan paths de Settings."""
        settings = _stub_settings(tmp_path)
        with patch("arca_mcp.config.get_server_settings", return_value=settings):
            result = validate_certificate()
        assert not isinstance(result, ArcaError)
        assert result.valid is False  # "CERT" no es un PEM válido
