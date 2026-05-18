"""Smoke tests para la carga de Settings al startup del servidor.

Verifica que:
- Settings lee ARCA_* env vars correctamente.
- Settings lee desde un archivo .env en el directorio de trabajo.
- init_server_settings() inicializa el singleton y get_server_settings() lo retorna.
- get_server_settings() lanza RuntimeError si no fue inicializado.
- El resolver usa el singleton del servidor cuando está disponible.
"""

import os
from pathlib import Path

import pytest

from arca_mcp.config_settings import Environment, Settings


# ---------------------------------------------------------------------------
# Carga desde env vars
# ---------------------------------------------------------------------------

class TestSettingsFromEnvVars:
    def test_reads_arca_environment(self, monkeypatch):
        """ARCA_ENVIRONMENT=homologacion → settings.environment == HOMOLOGACION."""
        monkeypatch.setenv("ARCA_ENVIRONMENT", "homologacion")
        # env_file=".env" no afecta si el archivo no existe; forzamos None para aislar
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
        assert settings.environment == Environment.HOMOLOGACION

    def test_reads_arca_cert_path(self, monkeypatch, tmp_path):
        """ARCA_CERT_PATH se carga como Path."""
        cert = tmp_path / "cert.crt"
        cert.write_text("CERT")
        monkeypatch.setenv("ARCA_CERT_PATH", str(cert))
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
        assert settings.cert_path == cert

    def test_reads_arca_key_path(self, monkeypatch, tmp_path):
        """ARCA_KEY_PATH se carga como Path."""
        key = tmp_path / "key.pem"
        key.write_text("KEY")
        monkeypatch.setenv("ARCA_KEY_PATH", str(key))
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
        assert settings.key_path == key

    def test_reads_arca_cuit(self, monkeypatch):
        """ARCA_CUIT se carga como str."""
        monkeypatch.setenv("ARCA_CUIT", "20123456789")
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
        assert settings.cuit == "20123456789"

    def test_defaults_when_no_env(self, monkeypatch):
        """Sin env vars configuradas, los defaults son homologacion y paths None."""
        monkeypatch.delenv("ARCA_ENVIRONMENT", raising=False)
        monkeypatch.delenv("ARCA_CERT_PATH", raising=False)
        monkeypatch.delenv("ARCA_KEY_PATH", raising=False)
        monkeypatch.delenv("ARCA_CUIT", raising=False)
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
        assert settings.environment == Environment.HOMOLOGACION
        assert settings.cert_path is None
        assert settings.key_path is None
        assert settings.cuit is None


# ---------------------------------------------------------------------------
# Carga desde archivo .env
# ---------------------------------------------------------------------------

class TestSettingsFromDotEnv:
    def test_reads_from_env_file(self, tmp_path, monkeypatch):
        """Settings carga correctamente desde un archivo .env en disco."""
        # Asegurar que env vars reales no interfieran
        monkeypatch.delenv("ARCA_ENVIRONMENT", raising=False)
        monkeypatch.delenv("ARCA_CERT_PATH", raising=False)
        monkeypatch.delenv("ARCA_KEY_PATH", raising=False)
        monkeypatch.delenv("ARCA_CUIT", raising=False)

        cert = tmp_path / "cert.crt"
        key = tmp_path / "key.pem"
        cert.write_text("CERT")
        key.write_text("KEY")

        env_file = tmp_path / ".env"
        env_file.write_text(
            f"ARCA_ENVIRONMENT=homologacion\n"
            f"ARCA_CERT_PATH={cert}\n"
            f"ARCA_KEY_PATH={key}\n"
            f"ARCA_CUIT=20987654321\n"
        )

        settings = Settings(_env_file=str(env_file))  # type: ignore[call-arg]
        assert settings.environment == Environment.HOMOLOGACION
        assert settings.cert_path == cert
        assert settings.key_path == key
        assert settings.cuit == "20987654321"


# ---------------------------------------------------------------------------
# Singleton del servidor
# ---------------------------------------------------------------------------

class TestServerSettingsSingleton:
    def test_init_and_get(self):
        """init_server_settings() inicializa; get_server_settings() retorna el mismo objeto."""
        import arca_mcp.config as cfg

        expected = Settings.model_construct(
            environment=Environment.HOMOLOGACION,
            cert_path=None,
            key_path=None,
            cuit="20000000000",
        )
        returned = cfg.init_server_settings(expected)
        assert returned is expected
        assert cfg.get_server_settings() is expected

        # Limpiar para no contaminar otros tests
        cfg._server_settings = None

    def test_get_raises_if_not_initialized(self):
        """get_server_settings() lanza RuntimeError si no fue inicializado."""
        import arca_mcp.config as cfg

        original = cfg._server_settings
        cfg._server_settings = None
        try:
            with pytest.raises(RuntimeError, match="init_server_settings"):
                cfg.get_server_settings()
        finally:
            cfg._server_settings = original

    def test_init_without_args_creates_real_settings(self, monkeypatch):
        """init_server_settings() sin args crea un Settings real desde env."""
        import arca_mcp.config as cfg

        monkeypatch.delenv("ARCA_ENVIRONMENT", raising=False)
        monkeypatch.delenv("ARCA_CERT_PATH", raising=False)
        monkeypatch.delenv("ARCA_KEY_PATH", raising=False)
        monkeypatch.delenv("ARCA_CUIT", raising=False)

        try:
            result = cfg.init_server_settings()
            assert isinstance(result, Settings)
            assert result.environment == Environment.HOMOLOGACION
        finally:
            cfg._server_settings = None


# ---------------------------------------------------------------------------
# Resolver usa el singleton cuando está disponible
# ---------------------------------------------------------------------------

class TestResolverUsesSingleton:
    def test_resolver_picks_up_singleton(self, tmp_path):
        """El resolver usa el singleton del servidor cuando _settings no se pasa."""
        import arca_mcp.config as cfg
        from arca_mcp.config import resolve_runtime_config
        from arca_mcp.config.resolver import RuntimeConfig

        cert = tmp_path / "cert.crt"
        key = tmp_path / "key.pem"
        cert.write_text("CERT")
        key.write_text("KEY")

        singleton = Settings.model_construct(
            environment=Environment.HOMOLOGACION,
            cert_path=cert,
            key_path=key,
            cuit="20111111111",
        )
        cfg.init_server_settings(singleton)
        try:
            result = resolve_runtime_config()
            assert isinstance(result, RuntimeConfig)
            assert result.cert_path == cert
            assert result.key_path == key
            assert result.emitter_cuit == "20111111111"
        finally:
            cfg._server_settings = None
