"""Tests de matriz para resolve_runtime_config.

Cubre todas las combinaciones de:
- defaults presentes / ausentes en Settings
- overrides presentes / ausentes / parciales
- environment válido / inválido / PRODUCCION
"""

from pathlib import Path

import pytest

from arca_mcp.config import ConfigOverrides, RuntimeConfig, resolve_runtime_config
from arca_mcp.config.settings import Environment, Settings
from arca_mcp.errors import ArcaError, ArcaErrorCause

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_settings(tmp_path: Path, *, cert: bool = True, key: bool = True, cuit: str | None = None) -> tuple[Settings, Path, Path]:
    """Crea un Settings con cert/key escritos a disco."""
    cert_path = tmp_path / "cert.crt"
    key_path = tmp_path / "key.pem"
    if cert:
        cert_path.write_text("CERT")
    if key:
        key_path.write_text("KEY")
    settings = Settings.model_construct(
        environment=Environment.HOMOLOGACION,
        cert_path=cert_path if cert else None,
        key_path=key_path if key else None,
        cuit=cuit,
    )
    return settings, cert_path, key_path


# ---------------------------------------------------------------------------
# Casos exitosos
# ---------------------------------------------------------------------------

class TestResolveSuccess:
    def test_server_defaults_only(self, tmp_path):
        """Solo defaults del servidor, sin overrides — debe resolver ok."""
        settings, cert_path, key_path = make_settings(tmp_path)
        result = resolve_runtime_config(_settings=settings)
        assert isinstance(result, RuntimeConfig)
        assert result.environment == Environment.HOMOLOGACION
        assert result.cert_path == cert_path
        assert result.key_path == key_path
        assert result.emitter_cuit is None

    def test_server_defaults_with_cuit(self, tmp_path):
        settings, cert_path, key_path = make_settings(tmp_path, cuit="20123456780")
        result = resolve_runtime_config(_settings=settings)
        assert isinstance(result, RuntimeConfig)
        assert result.emitter_cuit == "20123456780"

    def test_call_overrides_only(self, tmp_path):
        """Overrides por llamada completos, Settings sin paths — debe resolver ok."""
        cert_path = tmp_path / "cert.crt"
        key_path = tmp_path / "key.pem"
        cert_path.write_text("CERT")
        key_path.write_text("KEY")

        bare_settings = Settings.model_construct(
            environment=Environment.HOMOLOGACION,
            cert_path=None,
            key_path=None,
            cuit=None,
        )
        ov = ConfigOverrides(cert_path=cert_path, key_path=key_path)
        result = resolve_runtime_config(overrides=ov, _settings=bare_settings)
        assert isinstance(result, RuntimeConfig)
        assert result.cert_path == cert_path
        assert result.key_path == key_path

    def test_overrides_take_precedence_over_defaults(self, tmp_path):
        """Los overrides deben ganar sobre los defaults del servidor."""
        settings, _, _ = make_settings(tmp_path)

        override_dir = tmp_path / "override"
        override_dir.mkdir()
        ov_cert = override_dir / "cert.crt"
        ov_key = override_dir / "key.pem"
        ov_cert.write_text("CERT2")
        ov_key.write_text("KEY2")

        ov = ConfigOverrides(cert_path=ov_cert, key_path=ov_key)
        result = resolve_runtime_config(overrides=ov, _settings=settings)
        assert isinstance(result, RuntimeConfig)
        assert result.cert_path == ov_cert
        assert result.key_path == ov_key

    def test_override_emitter_cuit(self, tmp_path):
        """Override de emitter_cuit gana sobre el default del servidor."""
        settings, _, _ = make_settings(tmp_path, cuit="20000000000")
        ov = ConfigOverrides(emitter_cuit="20999999990")
        result = resolve_runtime_config(overrides=ov, _settings=settings)
        assert isinstance(result, RuntimeConfig)
        assert result.emitter_cuit == "20999999990"

    def test_no_overrides_argument(self, tmp_path):
        """Llamada sin argumento overrides (None) también funciona."""
        settings, _, _ = make_settings(tmp_path)
        result = resolve_runtime_config(None, _settings=settings)
        assert isinstance(result, RuntimeConfig)

    def test_runtime_config_is_immutable(self, tmp_path):
        """RuntimeConfig es frozen — mutación debe fallar."""
        settings, cert_path, key_path = make_settings(tmp_path)
        result = resolve_runtime_config(_settings=settings)
        assert isinstance(result, RuntimeConfig)
        with pytest.raises(Exception):
            result.environment = Environment.PRODUCCION  # type: ignore[misc]

    def test_runtime_config_is_hashable(self, tmp_path):
        """RuntimeConfig debe poder usarse como clave de dict/set."""
        settings, _, _ = make_settings(tmp_path)
        result = resolve_runtime_config(_settings=settings)
        assert isinstance(result, RuntimeConfig)
        d = {result: "value"}
        assert d[result] == "value"

    def test_two_identical_configs_have_same_hash(self, tmp_path):
        """Dos RuntimeConfig con los mismos valores deben tener el mismo hash."""
        settings, _, _ = make_settings(tmp_path)
        r1 = resolve_runtime_config(_settings=settings)
        r2 = resolve_runtime_config(_settings=settings)
        assert isinstance(r1, RuntimeConfig)
        assert isinstance(r2, RuntimeConfig)
        assert hash(r1) == hash(r2)
        assert r1 == r2


# ---------------------------------------------------------------------------
# MISSING_CONFIG
# ---------------------------------------------------------------------------

class TestMissingConfig:
    def test_missing_cert_path(self, tmp_path):
        """Falta cert_path en settings y no hay override → MISSING_CONFIG."""
        key_path = tmp_path / "key.pem"
        key_path.write_text("KEY")
        settings = Settings.model_construct(
            environment=Environment.HOMOLOGACION,
            cert_path=None,
            key_path=key_path,
            cuit=None,
        )
        result = resolve_runtime_config(_settings=settings)
        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.MISSING_CONFIG
        assert "cert_path" in result.message

    def test_missing_key_path(self, tmp_path):
        """Falta key_path en settings y no hay override → MISSING_CONFIG."""
        cert_path = tmp_path / "cert.crt"
        cert_path.write_text("CERT")
        settings = Settings.model_construct(
            environment=Environment.HOMOLOGACION,
            cert_path=cert_path,
            key_path=None,
            cuit=None,
        )
        result = resolve_runtime_config(_settings=settings)
        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.MISSING_CONFIG
        assert "key_path" in result.message

    def test_missing_both_paths(self, tmp_path):
        """Faltan ambos paths → MISSING_CONFIG (falla en cert_path primero)."""
        settings = Settings.model_construct(
            environment=Environment.HOMOLOGACION,
            cert_path=None,
            key_path=None,
            cuit=None,
        )
        result = resolve_runtime_config(_settings=settings)
        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.MISSING_CONFIG

    def test_cert_path_does_not_exist(self, tmp_path):
        """cert_path configurado pero no existe en disco → MISSING_CONFIG."""
        key_path = tmp_path / "key.pem"
        key_path.write_text("KEY")
        settings = Settings.model_construct(
            environment=Environment.HOMOLOGACION,
            cert_path=tmp_path / "nonexistent.crt",
            key_path=key_path,
            cuit=None,
        )
        result = resolve_runtime_config(_settings=settings)
        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.MISSING_CONFIG
        assert "cert_path" in result.message

    def test_key_path_does_not_exist(self, tmp_path):
        """key_path configurado pero no existe en disco → MISSING_CONFIG."""
        cert_path = tmp_path / "cert.crt"
        cert_path.write_text("CERT")
        settings = Settings.model_construct(
            environment=Environment.HOMOLOGACION,
            cert_path=cert_path,
            key_path=tmp_path / "nonexistent.pem",
            cuit=None,
        )
        result = resolve_runtime_config(_settings=settings)
        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.MISSING_CONFIG
        assert "key_path" in result.message


# ---------------------------------------------------------------------------
# INVALID_CONFIG_OVERRIDE
# ---------------------------------------------------------------------------

class TestInvalidConfigOverride:
    def test_only_cert_path_override(self, tmp_path):
        """Override con solo cert_path (sin key_path) → INVALID_CONFIG_OVERRIDE."""
        cert_path = tmp_path / "cert.crt"
        cert_path.write_text("CERT")
        settings, _, _ = make_settings(tmp_path)
        ov = ConfigOverrides(cert_path=cert_path, key_path=None)
        result = resolve_runtime_config(overrides=ov, _settings=settings)
        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.INVALID_CONFIG_OVERRIDE
        assert "key_path" in result.message

    def test_only_key_path_override(self, tmp_path):
        """Override con solo key_path (sin cert_path) → INVALID_CONFIG_OVERRIDE."""
        key_path = tmp_path / "key.pem"
        key_path.write_text("KEY")
        settings, _, _ = make_settings(tmp_path)
        ov = ConfigOverrides(key_path=key_path, cert_path=None)
        result = resolve_runtime_config(overrides=ov, _settings=settings)
        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.INVALID_CONFIG_OVERRIDE
        assert "cert_path" in result.message


# ---------------------------------------------------------------------------
# UNSUPPORTED_ENVIRONMENT
# ---------------------------------------------------------------------------

class TestUnsupportedEnvironment:
    def test_produccion_in_settings(self, tmp_path):
        """Settings con environment=PRODUCCION → UNSUPPORTED_ENVIRONMENT."""
        settings, _, _ = make_settings(tmp_path)
        settings = Settings.model_construct(
            environment=Environment.PRODUCCION,
            cert_path=settings.cert_path,
            key_path=settings.key_path,
            cuit=None,
        )
        result = resolve_runtime_config(_settings=settings)
        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.UNSUPPORTED_ENVIRONMENT
        assert "produccion" in result.message.lower()

    def test_produccion_via_override(self, tmp_path):
        """Override de environment=PRODUCCION → UNSUPPORTED_ENVIRONMENT."""
        settings, _, _ = make_settings(tmp_path)
        ov = ConfigOverrides(environment=Environment.PRODUCCION)
        result = resolve_runtime_config(overrides=ov, _settings=settings)
        assert isinstance(result, ArcaError)
        assert result.cause == ArcaErrorCause.UNSUPPORTED_ENVIRONMENT

    def test_invalid_environment_string_rejected(self):
        """ConfigOverrides con string inválido para environment → ValidationError de Pydantic."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ConfigOverrides(environment="invalid_env")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Caso 3: defaults parciales + overrides que completan
# ---------------------------------------------------------------------------

class TestPartialDefaultsCompletedByOverrides:
    def test_partial_defaults_no_cuit_override_provides_cuit(self, tmp_path):
        """Settings tiene cert+key pero no cuit; override provee cuit → RuntimeConfig OK."""
        settings, cert_path, key_path = make_settings(tmp_path, cuit=None)
        ov = ConfigOverrides(emitter_cuit="20111111110")
        result = resolve_runtime_config(overrides=ov, _settings=settings)
        assert isinstance(result, RuntimeConfig)
        assert result.cert_path == cert_path
        assert result.key_path == key_path
        assert result.emitter_cuit == "20111111110"

    def test_partial_defaults_no_paths_override_provides_paths(self, tmp_path):
        """Settings tiene environment y cuit pero no paths; override provee cert+key → RuntimeConfig OK."""
        override_cert = tmp_path / "ov_cert.crt"
        override_key = tmp_path / "ov_key.pem"
        override_cert.write_text("CERT")
        override_key.write_text("KEY")

        partial_settings = Settings.model_construct(
            environment=Environment.HOMOLOGACION,
            cert_path=None,
            key_path=None,
            cuit="20222222220",
        )
        ov = ConfigOverrides(cert_path=override_cert, key_path=override_key)
        result = resolve_runtime_config(overrides=ov, _settings=partial_settings)
        assert isinstance(result, RuntimeConfig)
        assert result.cert_path == override_cert
        assert result.key_path == override_key
        assert result.emitter_cuit == "20222222220"
