"""Unit tests for arca_mcp.wsaa.token_cache.TokenCache."""

import datetime
import stat
from pathlib import Path

import pytest

from arca_mcp.wsaa.models import WsaaToken
from arca_mcp.wsaa.token_cache import TokenCache

CUIT = "20123456789"


def _future(minutes: int = 60) -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=minutes)


def _past(minutes: int = 10) -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=minutes)


def _make_token(expiration_time: datetime.datetime) -> WsaaToken:
    return WsaaToken(
        token="dummy-token",
        sign="dummy-sign",
        generation_time=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        expiration_time=expiration_time.isoformat(),
    )


@pytest.fixture
def cache(tmp_path: Path) -> TokenCache:
    return TokenCache(cache_dir=tmp_path / "tokens")


class TestTokenCacheGet:
    def test_hit_returns_token(self, cache: TokenCache):
        token = _make_token(_future())
        cache.save(CUIT, token)
        result = cache.get(CUIT)
        assert result is not None
        assert result.token == token.token
        assert result.sign == token.sign

    def test_miss_by_absence(self, cache: TokenCache):
        assert cache.get(CUIT) is None

    def test_miss_by_expired_token(self, cache: TokenCache):
        cache.save(CUIT, _make_token(_past()))
        assert cache.get(CUIT) is None

    def test_expired_file_evicted_on_read(self, cache: TokenCache):
        cache.save(CUIT, _make_token(_past()))
        cache.get(CUIT)
        assert not cache._path(CUIT).exists()

    def test_different_cuits_are_independent(self, cache: TokenCache):
        t1 = _make_token(_future())
        t2 = _make_token(_future(minutes=30))
        cache.save("20111111111", t1)
        cache.save("20222222222", t2)
        assert cache.get("20111111111").token == t1.token
        assert cache.get("20222222222").token == t2.token


class TestTokenCacheSave:
    def test_file_permissions_0600(self, cache: TokenCache):
        cache.save(CUIT, _make_token(_future()))
        path = cache._path(CUIT)
        assert stat.S_IMODE(path.stat().st_mode) == 0o600

    def test_creates_directory_if_missing(self, tmp_path: Path):
        deep_cache = TokenCache(cache_dir=tmp_path / "a" / "b" / "tokens")
        deep_cache.save(CUIT, _make_token(_future()))
        assert deep_cache._path(CUIT).exists()

    def test_overwrite_replaces_token(self, cache: TokenCache):
        cache.save(CUIT, _make_token(_future(minutes=30)))
        new_token = _make_token(_future(minutes=60))
        cache.save(CUIT, new_token)
        result = cache.get(CUIT)
        assert result is not None
        assert result.expiration_time == new_token.expiration_time


class TestTokenCacheInvalidate:
    def test_invalidate_removes_cached_token(self, cache: TokenCache):
        cache.save(CUIT, _make_token(_future()))
        cache.invalidate(CUIT)
        assert cache.get(CUIT) is None

    def test_invalidate_nonexistent_is_noop(self, cache: TokenCache):
        cache.invalidate(CUIT)  # must not raise
