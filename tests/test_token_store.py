"""Unit tests for arca_mcp.wsaa.token_store."""

import datetime

import pytest

from arca_mcp.wsaa import token_store


CERT = "/fake/cert.crt"
KEY = "/fake/key.pem"
ENV = "homologacion"
SVC = "wsfe"
TOKEN = "dummy-token"
SIGN = "dummy-sign"


@pytest.fixture(autouse=True)
def clean_store():
    """Ensure the store is empty before and after every test."""
    token_store.clear_store()
    yield
    token_store.clear_store()


def _future(minutes: int) -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=minutes)


def _past(minutes: int) -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=minutes)


class TestGetToken:
    def test_hit_returns_token_and_sign(self):
        """A token with plenty of time left should be returned."""
        token_store.put_token(CERT, KEY, ENV, SVC, TOKEN, SIGN, _future(60))
        result = token_store.get_token(CERT, KEY, ENV, SVC)
        assert result == (TOKEN, SIGN)

    def test_miss_returns_none(self):
        """A key that was never stored should return None."""
        result = token_store.get_token(CERT, KEY, ENV, SVC)
        assert result is None

    def test_expired_returns_none(self):
        """A token already past its expiration time should be treated as a miss."""
        token_store.put_token(CERT, KEY, ENV, SVC, TOKEN, SIGN, _past(10))
        result = token_store.get_token(CERT, KEY, ENV, SVC)
        assert result is None

    def test_expiring_soon_returns_none(self):
        """A token expiring in less than 5 minutes should be treated as a miss."""
        token_store.put_token(CERT, KEY, ENV, SVC, TOKEN, SIGN, _future(3))
        result = token_store.get_token(CERT, KEY, ENV, SVC)
        assert result is None

    def test_expired_entry_is_evicted(self):
        """After a miss due to expiry the entry should be removed from the store."""
        token_store.put_token(CERT, KEY, ENV, SVC, TOKEN, SIGN, _past(1))
        token_store.get_token(CERT, KEY, ENV, SVC)  # triggers eviction
        # A second call must also return None (not raise KeyError or similar).
        assert token_store.get_token(CERT, KEY, ENV, SVC) is None

    def test_different_keys_are_independent(self):
        """Entries under different keys must not interfere with each other."""
        token_store.put_token(CERT, KEY, ENV, "wsfe", TOKEN, SIGN, _future(60))
        token_store.put_token(CERT, KEY, ENV, "wsfex", "t2", "s2", _future(60))

        assert token_store.get_token(CERT, KEY, ENV, "wsfe") == (TOKEN, SIGN)
        assert token_store.get_token(CERT, KEY, ENV, "wsfex") == ("t2", "s2")


class TestClearStore:
    def test_clear_empties_the_store(self):
        """After clear_store every key should return None."""
        token_store.put_token(CERT, KEY, ENV, SVC, TOKEN, SIGN, _future(60))
        token_store.clear_store()
        assert token_store.get_token(CERT, KEY, ENV, SVC) is None

    def test_clear_on_empty_store_does_not_raise(self):
        """Calling clear_store on an already-empty store must not raise."""
        token_store.clear_store()  # store is already empty (autouse fixture)
