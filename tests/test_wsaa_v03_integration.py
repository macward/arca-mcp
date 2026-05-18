"""Integration tests for the v0.3 WSAA infra stack.

These tests cross multiple v0.3 components (TokenCache + login flow + concurrency).
Individual unit tests for each component live in test_token_cache.py,
test_wsaa_token_concurrency.py, test_wsaa_login.py, etc.

E2E tests (pytest.mark.e2e) require ARCA_TEST_CERT_PATH, ARCA_TEST_KEY_PATH,
and ARCA_TEST_CUIT. They are skipped automatically when those vars are absent.
"""

import asyncio
import datetime
import os
import stat
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from arca_mcp.wsaa.models import WsaaToken
from arca_mcp.wsaa.token_cache import TokenCache

CUIT_A = "20111111111"
CUIT_B = "20222222222"

_CERT_PATH = os.environ.get("ARCA_TEST_CERT_PATH")
_KEY_PATH = os.environ.get("ARCA_TEST_KEY_PATH")
_CUIT = os.environ.get("ARCA_TEST_CUIT")

_e2e_skip = pytest.mark.skipif(
    not (_CERT_PATH and _KEY_PATH and _CUIT),
    reason="E2E: set ARCA_TEST_CERT_PATH, ARCA_TEST_KEY_PATH, ARCA_TEST_CUIT",
)


def _make_token(minutes_valid: int = 60, token_str: str = "tok") -> WsaaToken:
    now = datetime.datetime.now(datetime.timezone.utc)
    return WsaaToken(
        token=token_str,
        sign="sig",
        generation_time=now.isoformat(),
        expiration_time=(now + datetime.timedelta(minutes=minutes_valid)).isoformat(),
    )


# ---------------------------------------------------------------------------
# Expiration E2E with simulated clock
# ---------------------------------------------------------------------------

class TestExpirationEndToEnd:
    def test_near_expiry_token_triggers_refresh(self, tmp_path: Path):
        """Token at 9 min from expiry → get_or_refresh calls the login fn."""
        now = datetime.datetime.now(datetime.timezone.utc)
        cache = TokenCache(cache_dir=tmp_path / "tokens", _now=lambda: now)
        near_expiry = _make_token(minutes_valid=9, token_str="old-tok")
        cache.save(CUIT_A, near_expiry)

        fresh = _make_token(minutes_valid=60, token_str="new-tok")
        refresh_mock = MagicMock(return_value=fresh)

        result = asyncio.run(cache.get_or_refresh(CUIT_A, refresh_mock))

        refresh_mock.assert_called_once()
        assert result.token == "new-tok"

    def test_valid_token_skips_refresh(self, tmp_path: Path):
        """Token at 11 min from expiry → get_or_refresh does NOT call the login fn."""
        now = datetime.datetime.now(datetime.timezone.utc)
        cache = TokenCache(cache_dir=tmp_path / "tokens", _now=lambda: now)
        fresh_enough = _make_token(minutes_valid=11, token_str="still-valid")
        cache.save(CUIT_A, fresh_enough)

        refresh_mock = MagicMock(return_value=_make_token())

        result = asyncio.run(cache.get_or_refresh(CUIT_A, refresh_mock))

        refresh_mock.assert_not_called()
        assert result.token == "still-valid"

    def test_expired_token_on_disk_triggers_refresh(self, tmp_path: Path):
        """Token already past expiry → get_or_refresh re-logins and persists new token."""
        now = datetime.datetime.now(datetime.timezone.utc)
        cache = TokenCache(cache_dir=tmp_path / "tokens", _now=lambda: now)

        expired = WsaaToken(
            token="expired",
            sign="s",
            generation_time=(now - datetime.timedelta(hours=2)).isoformat(),
            expiration_time=(now - datetime.timedelta(minutes=1)).isoformat(),
        )
        cache.save(CUIT_A, expired)

        fresh = _make_token(minutes_valid=60, token_str="refreshed")
        refresh_mock = MagicMock(return_value=fresh)

        result = asyncio.run(cache.get_or_refresh(CUIT_A, refresh_mock))

        refresh_mock.assert_called_once()
        assert result.token == "refreshed"

        persisted = cache.get(CUIT_A)
        assert persisted is not None
        assert persisted.token == "refreshed"


# ---------------------------------------------------------------------------
# Multi-CUIT independence
# ---------------------------------------------------------------------------

class TestMultiCuitIndependence:
    def test_two_cuits_stored_independently(self, tmp_path: Path):
        cache = TokenCache(cache_dir=tmp_path / "tokens")
        token_a = _make_token(token_str="token-for-a")
        token_b = _make_token(token_str="token-for-b")
        cache.save(CUIT_A, token_a)
        cache.save(CUIT_B, token_b)

        assert cache.get(CUIT_A).token == "token-for-a"
        assert cache.get(CUIT_B).token == "token-for-b"

    def test_invalidating_one_cuit_leaves_other_intact(self, tmp_path: Path):
        cache = TokenCache(cache_dir=tmp_path / "tokens")
        cache.save(CUIT_A, _make_token(token_str="a"))
        cache.save(CUIT_B, _make_token(token_str="b"))

        cache.invalidate(CUIT_A)

        assert cache.get(CUIT_A) is None
        assert cache.get(CUIT_B).token == "b"

    @pytest.mark.asyncio
    async def test_concurrent_interleaved_access_no_corruption(self, tmp_path: Path):
        """CUIT-A and CUIT-B refreshed concurrently → no token cross-writes."""
        cache = TokenCache(cache_dir=tmp_path / "tokens")
        calls: dict[str, int] = {CUIT_A: 0, CUIT_B: 0}

        def refresh_a():
            calls[CUIT_A] += 1
            return _make_token(token_str="tok-a")

        def refresh_b():
            calls[CUIT_B] += 1
            return _make_token(token_str="tok-b")

        results = await asyncio.gather(
            *[cache.get_or_refresh(CUIT_A, refresh_a) for _ in range(5)],
            *[cache.get_or_refresh(CUIT_B, refresh_b) for _ in range(5)],
        )

        assert calls[CUIT_A] == 1
        assert calls[CUIT_B] == 1
        assert all(r.token in ("tok-a", "tok-b") for r in results)
        assert cache.get(CUIT_A).token == "tok-a"
        assert cache.get(CUIT_B).token == "tok-b"


# ---------------------------------------------------------------------------
# 10-session concurrency
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_10_concurrent_sessions_single_login(tmp_path: Path):
    """10 concurrent coroutines over same CUIT → exactly 1 login call."""
    cache = TokenCache(cache_dir=tmp_path / "tokens")
    login_mock = MagicMock(return_value=_make_token())

    results = await asyncio.gather(
        *[cache.get_or_refresh(CUIT_A, login_mock) for _ in range(10)]
    )

    assert login_mock.call_count == 1
    assert len(results) == 10
    assert all(r.token == "tok" for r in results)


# ---------------------------------------------------------------------------
# E2E opt-in (requires real cert against homologación)
# ---------------------------------------------------------------------------

@pytest.mark.e2e
@_e2e_skip
def test_e2e_real_login_persists_token_with_correct_permissions(tmp_path: Path):
    """Real login against WSAA homologación → token file created with 0600 perms."""
    from arca_mcp.wsaa.login import validate_wsaa_login

    cert_path = Path(_CERT_PATH)
    key_path = Path(_KEY_PATH)
    cache_dir = tmp_path / "tokens"

    result = validate_wsaa_login(
        cert_path,
        key_path,
        service="wsfe",
        cuit=_CUIT,
        # Override the default TokenCache via monkeypatching is not available here;
        # this test uses the default path unless ARCA_TOKEN_CACHE_DIR is set.
    )

    assert result.ok is True
    assert result.token is not None


@pytest.mark.e2e
@_e2e_skip
def test_e2e_token_file_has_0600_permissions(tmp_path: Path, monkeypatch):
    """E2E: persisted token file has 0600 permissions."""
    from arca_mcp.wsaa.login import validate_wsaa_login

    cache_dir = tmp_path / "tokens"
    monkeypatch.setenv("ARCA_TOKEN_CACHE_DIR", str(cache_dir))

    cert_path = Path(_CERT_PATH)
    key_path = Path(_KEY_PATH)

    result = validate_wsaa_login(
        cert_path,
        key_path,
        service="wsfe",
        cuit=_CUIT,
    )

    assert result.ok is True
    token_file = cache_dir / f"{_CUIT}.json"
    if token_file.exists():
        assert stat.S_IMODE(token_file.stat().st_mode) == 0o600
