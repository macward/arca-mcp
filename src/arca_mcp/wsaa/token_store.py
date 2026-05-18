"""In-memory cache for WSAA tokens.

Key: (cert_path, key_path, environment, service)
Value: (token, sign, expiration_time)

A token is considered valid if its expiration_time is more than 5 minutes in the future.
"""

import datetime
from typing import Optional

# Module-level store: no singletons, just a plain dict.
_STORE: dict[
    tuple[str, str, str, str],
    tuple[str, str, datetime.datetime],
] = {}

_VALIDITY_BUFFER = datetime.timedelta(minutes=10)


def _to_aware_utc(value: datetime.datetime | str) -> datetime.datetime:
    """Normalize a datetime or ISO string to an aware UTC datetime."""
    if isinstance(value, str):
        value = datetime.datetime.fromisoformat(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=datetime.timezone.utc)
    return value.astimezone(datetime.timezone.utc)


def get_token(
    cert_path: str,
    key_path: str,
    environment: str,
    service: str,
) -> Optional[tuple[str, str]]:
    """Return (token, sign) if a valid cached token exists, else None.

    A token is valid when its expiration_time > utcnow() + 5 minutes.
    Expired entries are removed from the store on access.
    """
    key = (cert_path, key_path, environment, service)
    entry = _STORE.get(key)
    if entry is None:
        return None

    token, sign, expiration_time = entry
    expiration_time = _to_aware_utc(expiration_time)
    now = datetime.datetime.now(datetime.timezone.utc)
    if expiration_time > now + _VALIDITY_BUFFER:
        return token, sign

    # Token is expired or about to expire — evict it.
    del _STORE[key]
    return None


def put_token(
    cert_path: str,
    key_path: str,
    environment: str,
    service: str,
    token: str,
    sign: str,
    expiration_time: datetime.datetime | str,
) -> None:
    """Store a token under the given key."""
    key = (cert_path, key_path, environment, service)
    _STORE[key] = (token, sign, _to_aware_utc(expiration_time))


def clear_store() -> None:
    """Remove all entries from the in-memory store."""
    _STORE.clear()
