"""Concurrency tests for WsaaCache.get_or_refresh() and validate_wsaa_login()."""

import asyncio
import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from arca_mcp.wsaa.login import validate_wsaa_login
from arca_mcp.wsaa.models import WsaaToken
from arca_mcp.wsaa.wsaa_cache import WsaaCache

CUIT_A = "20111111111"
CUIT_B = "20222222222"
SVC = "wsfe"


def _make_token(minutes_valid: int = 60) -> WsaaToken:
    now = datetime.datetime.now(datetime.timezone.utc)
    return WsaaToken(
        token="tok",
        sign="sig",
        generation_time=now.isoformat(),
        expiration_time=(now + datetime.timedelta(minutes=minutes_valid)).isoformat(),
    )


@pytest.fixture
def cache(tmp_path: Path) -> WsaaCache:
    return WsaaCache(cache_dir=tmp_path / "tokens")


@pytest.mark.asyncio
async def test_concurrent_sessions_trigger_single_login(cache: WsaaCache):
    """10 concurrent coroutines should produce exactly 1 login call."""
    refresh_mock = MagicMock(return_value=_make_token())

    results = await asyncio.gather(
        *[cache.get_or_refresh(CUIT_A, SVC, refresh_mock) for _ in range(10)]
    )

    assert refresh_mock.call_count == 1
    assert all(r.token == "tok" for r in results)


@pytest.mark.asyncio
async def test_independent_locks_per_cuit(cache: WsaaCache):
    """Two different CUITs use independent locks — no mutual blocking."""
    calls: dict[str, int] = {CUIT_A: 0, CUIT_B: 0}

    def refresh_a() -> WsaaToken:
        calls[CUIT_A] += 1
        return _make_token()

    def refresh_b() -> WsaaToken:
        calls[CUIT_B] += 1
        return _make_token()

    results = await asyncio.gather(
        *[cache.get_or_refresh(CUIT_A, SVC, refresh_a) for _ in range(5)],
        *[cache.get_or_refresh(CUIT_B, SVC, refresh_b) for _ in range(5)],
    )

    assert calls[CUIT_A] == 1
    assert calls[CUIT_B] == 1
    assert len(results) == 10
    # Locks for A and B must be distinct objects
    assert cache._get_fs_lock(CUIT_A) is not cache._get_fs_lock(CUIT_B)


@pytest.mark.asyncio
async def test_cache_hit_bypasses_refresh(cache: WsaaCache):
    """If token is already in cache, refresh_fn is never called."""
    cache.save(CUIT_A, _make_token())
    refresh_mock = MagicMock(return_value=_make_token())

    result = await cache.get_or_refresh(CUIT_A, SVC, refresh_mock)

    refresh_mock.assert_not_called()
    assert result.token == "tok"


@pytest.mark.asyncio
async def test_second_waiter_uses_cached_result(cache: WsaaCache):
    """After the first coroutine refreshes, the second must use the cached result."""
    call_count = 0

    def _do_login() -> WsaaToken:
        nonlocal call_count
        call_count += 1
        return _make_token()

    results = await asyncio.gather(
        cache.get_or_refresh(CUIT_A, SVC, _do_login),
        cache.get_or_refresh(CUIT_A, SVC, _do_login),
        cache.get_or_refresh(CUIT_A, SVC, _do_login),
    )

    assert call_count == 1
    assert all(r.token == "tok" for r in results)


# ---------------------------------------------------------------------------
# Production path: validate_wsaa_login() with concurrent callers
# ---------------------------------------------------------------------------

SUCCESS_RESPONSE = """<?xml version="1.0"?>
<loginTicketResponse>
  <header>
    <uniqueId>1</uniqueId>
    <generationTime>2026-05-16T10:00:00-03:00</generationTime>
    <expirationTime>2099-05-16T22:00:00-03:00</expirationTime>
  </header>
  <credentials>
    <token>TOKEN123</token>
    <sign>SIGN456</sign>
  </credentials>
</loginTicketResponse>"""


@pytest.mark.asyncio
async def test_validate_wsaa_login_concurrent_single_network_call(
    tmp_path: Path, mocker, cert_key_pair
):
    """10 concurrent calls to validate_wsaa_login() with the same CUIT produce exactly 1 WSAA request."""
    cert_path, key_path = cert_key_pair
    call_login = mocker.patch(
        "arca_mcp.wsaa.login.call_login_cms",
        return_value=SUCCESS_RESPONSE,
    )
    fs_cache = WsaaCache(cache_dir=tmp_path / "tokens")

    results = await asyncio.gather(
        *[
            validate_wsaa_login(cert_path, key_path, cuit=CUIT_A, cache=fs_cache)
            for _ in range(10)
        ]
    )

    assert call_login.call_count == 1
    assert all(r.ok for r in results)
    assert all(r.token is not None and r.token.token == "TOKEN123" for r in results)


@pytest.mark.asyncio
async def test_lock_released_after_refresh_fn_raises(cache: WsaaCache):
    """If refresh_fn raises, the lock is released so subsequent callers can retry."""

    def _failing_login() -> WsaaToken:
        raise ValueError("WSAA unreachable")

    with pytest.raises(ValueError, match="WSAA unreachable"):
        await cache.get_or_refresh(CUIT_A, SVC, _failing_login)

    assert not cache._get_fs_lock(CUIT_A).locked()

    result = await cache.get_or_refresh(CUIT_A, SVC, lambda: _make_token())
    assert result.token == "tok"
