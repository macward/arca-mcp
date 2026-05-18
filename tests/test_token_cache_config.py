"""Tests for TokenCache directory configuration via ARCA_TOKEN_CACHE_DIR."""

import os
from pathlib import Path

import pytest

from arca_mcp.wsaa.token_cache import TokenCache, _ENV_VAR


class TestCacheDirConfiguration:
    def test_explicit_cache_dir_is_used(self, tmp_path: Path):
        custom = tmp_path / "my-cache"
        cache = TokenCache(cache_dir=custom)
        assert cache._cache_dir == custom

    def test_env_var_sets_cache_dir(self, tmp_path: Path, monkeypatch):
        env_path = tmp_path / "env-cache"
        monkeypatch.setenv(_ENV_VAR, str(env_path))
        cache = TokenCache()
        assert cache._cache_dir == env_path

    def test_env_var_overrides_default(self, tmp_path: Path, monkeypatch):
        env_path = tmp_path / "override"
        monkeypatch.setenv(_ENV_VAR, str(env_path))
        cache = TokenCache()
        default = Path.home() / ".arca-mcp" / "tokens"
        assert cache._cache_dir != default
        assert cache._cache_dir == env_path

    def test_explicit_param_overrides_env_var(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv(_ENV_VAR, str(tmp_path / "env-path"))
        explicit = tmp_path / "explicit-path"
        cache = TokenCache(cache_dir=explicit)
        assert cache._cache_dir == explicit

    def test_default_used_when_no_env_var(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv(_ENV_VAR, raising=False)
        # Use explicit path to avoid touching ~/.arca-mcp in tests
        cache = TokenCache(cache_dir=tmp_path / "tokens")
        assert cache._cache_dir == tmp_path / "tokens"

    def test_directory_created_on_init(self, tmp_path: Path):
        new_dir = tmp_path / "brand-new" / "nested"
        assert not new_dir.exists()
        TokenCache(cache_dir=new_dir)
        assert new_dir.exists()

    def test_unwritable_directory_raises_value_error(self, tmp_path: Path):
        locked = tmp_path / "locked"
        locked.mkdir(mode=0o500)  # r-x: no write
        try:
            with pytest.raises(ValueError, match="no es escribible"):
                TokenCache(cache_dir=locked)
        finally:
            locked.chmod(0o700)  # restore so tmp cleanup works
