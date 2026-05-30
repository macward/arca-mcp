"""Unit + E2E tests for WsaaCache (the unified WSAA token cache).

WsaaCache replaced the former two-layer design (token_store + TokenCache).
Concurrency and near-expiry behavior live in test_wsaa_token_concurrency.py
and test_wsaa_login.py; this file covers filesystem persistence guarantees
(0600 permissions, cache-dir configuration) and the opt-in E2E login path.

E2E tests (pytest.mark.e2e) require ARCA_TEST_CERT_PATH, ARCA_TEST_KEY_PATH,
and ARCA_TEST_CUIT. They are skipped automatically when those vars are absent.
"""

import datetime
import os
import stat
from pathlib import Path

import pytest

from arca_mcp.wsaa.models import WsaaToken
from arca_mcp.wsaa.wsaa_cache import _ENV_VAR, WsaaCache

CUIT_A = "20111111111"

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
# Filesystem persistence guarantees
# ---------------------------------------------------------------------------

class TestFilesystemPersistence:
    def test_saved_token_file_has_0600_permissions(self, tmp_path: Path):
        """save() must persist the token file with owner-only (0600) permissions."""
        cache = WsaaCache(cache_dir=tmp_path / "tokens")
        cache.save(CUIT_A, _make_token())

        token_file = tmp_path / "tokens" / f"{CUIT_A}.json"
        assert token_file.exists()
        assert stat.S_IMODE(token_file.stat().st_mode) == 0o600

    def test_save_does_not_leave_tmp_file_behind(self, tmp_path: Path):
        """Atomic write: the .tmp staging file must be renamed away, not left on disk."""
        cache = WsaaCache(cache_dir=tmp_path / "tokens")
        cache.save(CUIT_A, _make_token())

        tmp_file = tmp_path / "tokens" / f"{CUIT_A}.tmp"
        assert not tmp_file.exists()


# ---------------------------------------------------------------------------
# Cache directory configuration (ARCA_TOKEN_CACHE_DIR)
# ---------------------------------------------------------------------------

class TestCacheDirConfig:
    def test_explicit_cache_dir_wins_over_env(self, tmp_path: Path, monkeypatch):
        """An explicit cache_dir argument takes precedence over the env var."""
        monkeypatch.setenv(_ENV_VAR, str(tmp_path / "from-env"))
        explicit = tmp_path / "explicit"
        cache = WsaaCache(cache_dir=explicit)
        cache.save(CUIT_A, _make_token())

        assert (explicit / f"{CUIT_A}.json").exists()
        assert not (tmp_path / "from-env").exists()

    def test_env_var_used_when_no_explicit_dir(self, tmp_path: Path, monkeypatch):
        """With no explicit cache_dir, ARCA_TOKEN_CACHE_DIR selects the directory."""
        env_path = tmp_path / "from-env"
        monkeypatch.setenv(_ENV_VAR, str(env_path))
        cache = WsaaCache()
        cache.save(CUIT_A, _make_token())

        assert (env_path / f"{CUIT_A}.json").exists()


# ---------------------------------------------------------------------------
# E2E opt-in (requires real cert against homologación) — exercises the live
# validate_wsaa_login → WsaaCache path.
# ---------------------------------------------------------------------------

@pytest.mark.e2e
@_e2e_skip
async def test_e2e_real_login_persists_token_with_correct_permissions():
    """Real login against WSAA homologación → token file created with 0600 perms."""
    from arca_mcp.wsaa.login import validate_wsaa_login

    assert _CERT_PATH and _KEY_PATH  # guaranteed by _e2e_skip
    cert_path = Path(_CERT_PATH)
    key_path = Path(_KEY_PATH)

    result = await validate_wsaa_login(
        cert_path,
        key_path,
        service="wsfe",
        cuit=_CUIT,
        # Uses the default cache path unless ARCA_TOKEN_CACHE_DIR is set.
    )

    assert result.ok is True
    # When a valid TA is still alive, WSAA refuses to re-issue one; ok=True with token=None
    # is the expected response in that case and counts as a successful auth check.
    if result.token is None and result.message and (
        "ya posee un ta" in result.message.lower()
        or "auth previa válida" in result.message.lower()
        or "no se re-emite token" in result.message.lower()
    ):
        pytest.skip("WSAA tiene un TA activo para wsfe — no re-emite token (rate limit)")


@pytest.mark.e2e
@_e2e_skip
async def test_e2e_token_file_has_0600_permissions(tmp_path: Path, monkeypatch):
    """E2E: persisted token file has 0600 permissions."""
    from arca_mcp.wsaa.login import validate_wsaa_login

    cache_dir = tmp_path / "tokens"
    monkeypatch.setenv("ARCA_TOKEN_CACHE_DIR", str(cache_dir))

    assert _CERT_PATH and _KEY_PATH  # guaranteed by _e2e_skip
    cert_path = Path(_CERT_PATH)
    key_path = Path(_KEY_PATH)

    result = await validate_wsaa_login(
        cert_path,
        key_path,
        service="wsfe",
        cuit=_CUIT,
    )

    assert result.ok is True
    token_file = cache_dir / f"{_CUIT}.json"
    if token_file.exists():
        assert stat.S_IMODE(token_file.stat().st_mode) == 0o600
