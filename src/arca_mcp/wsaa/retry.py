"""Retry utility for transient WSAA network failures.

Only retries on explicitly retryable exceptions (ConnectError, TimeoutException).
Business errors (auth failures, invalid certs) propagate immediately.
"""

import time
from collections.abc import Callable
from typing import TypeVar

import httpx

T = TypeVar("T")

RETRYABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (
    httpx.ConnectError,
    httpx.TimeoutException,
)

_DEFAULT_DELAYS: tuple[float, ...] = (0.1, 0.5)


def with_retry(
    fn: Callable[[], T],
    max_attempts: int = 2,
    delays: tuple[float, ...] = _DEFAULT_DELAYS,
    retryable_exceptions: tuple[type[BaseException], ...] = RETRYABLE_EXCEPTIONS,
) -> T:
    """Call fn up to max_attempts times, sleeping delays[i] between attempts.

    Raises the last exception if all attempts fail.
    Non-retryable exceptions propagate immediately without retry.
    """
    last_exc: BaseException | None = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except retryable_exceptions as exc:
            last_exc = exc
            if attempt < max_attempts - 1 and attempt < len(delays):
                time.sleep(delays[attempt])
    assert last_exc is not None
    raise last_exc
