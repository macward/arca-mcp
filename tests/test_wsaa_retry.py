"""Unit tests for arca_mcp.wsaa.retry.with_retry."""

import httpx
import pytest

from arca_mcp.wsaa.retry import with_retry


class TestWithRetry:
    def test_succeeds_on_first_attempt(self):
        calls = {"n": 0}

        def fn():
            calls["n"] += 1
            return "ok"

        result = with_retry(fn)
        assert result == "ok"
        assert calls["n"] == 1

    def test_retries_on_transient_error_and_succeeds(self, mocker):
        mocker.patch("arca_mcp.wsaa.retry.time.sleep")
        calls = {"n": 0}

        def fn():
            calls["n"] += 1
            if calls["n"] == 1:
                raise httpx.ConnectError("boom")
            return "ok"

        result = with_retry(fn, max_attempts=2)
        assert result == "ok"
        assert calls["n"] == 2

    def test_raises_after_all_attempts_exhausted(self, mocker):
        mocker.patch("arca_mcp.wsaa.retry.time.sleep")

        def fn():
            raise httpx.ConnectError("nope")

        with pytest.raises(httpx.ConnectError):
            with_retry(fn, max_attempts=2)

    def test_timeout_exception_is_retried(self, mocker):
        mocker.patch("arca_mcp.wsaa.retry.time.sleep")
        calls = {"n": 0}

        def fn():
            calls["n"] += 1
            if calls["n"] < 2:
                raise httpx.TimeoutException("slow")
            return "ok"

        result = with_retry(fn, max_attempts=2)
        assert result == "ok"
        assert calls["n"] == 2

    def test_non_retryable_exception_propagates_immediately(self, mocker):
        mocker.patch("arca_mcp.wsaa.retry.time.sleep")
        calls = {"n": 0}

        def fn():
            calls["n"] += 1
            raise ValueError("business error")

        with pytest.raises(ValueError, match="business error"):
            with_retry(fn, max_attempts=3)

        assert calls["n"] == 1

    def test_sleep_delays_between_attempts(self, mocker):
        sleep_mock = mocker.patch("arca_mcp.wsaa.retry.time.sleep")
        calls = {"n": 0}

        def fn():
            calls["n"] += 1
            if calls["n"] < 3:
                raise httpx.ConnectError("fail")
            return "ok"

        with_retry(fn, max_attempts=3, delays=(0.1, 0.5))
        assert sleep_mock.call_count == 2
        sleep_mock.assert_any_call(0.1)
        sleep_mock.assert_any_call(0.5)

    def test_correct_attempt_count(self, mocker):
        mocker.patch("arca_mcp.wsaa.retry.time.sleep")
        calls = {"n": 0}

        def fn():
            calls["n"] += 1
            raise httpx.ConnectError("fail")

        with pytest.raises(httpx.ConnectError):
            with_retry(fn, max_attempts=3)

        assert calls["n"] == 3
