"""Unit tests for arca_mcp.wsaa.wsaa_logger."""

import json
import logging

import pytest

from arca_mcp.wsaa.wsaa_logger import WsaaCallResult, log_wsaa_call


@pytest.fixture
def wsaa_log_records(caplog):
    with caplog.at_level(logging.INFO, logger="arca_mcp.wsaa.calls"):
        yield caplog


def _capture_log_json(caplog) -> dict:
    assert len(caplog.messages) == 1, f"Expected 1 log message, got {len(caplog.messages)}"
    return json.loads(caplog.messages[0])


class TestLogWsaaCall:
    def test_ok_result_has_required_fields(self, wsaa_log_records):
        log_wsaa_call("20123456789", "wsfe", 123, WsaaCallResult.OK)
        entry = _capture_log_json(wsaa_log_records)
        assert entry["cuit"] == "20123456789"
        assert entry["service"] == "wsfe"
        assert entry["latency_ms"] == 123
        assert entry["result"] == "ok"
        assert "ts" in entry
        assert "error_cause" not in entry

    def test_cached_result(self, wsaa_log_records):
        log_wsaa_call("20123456789", "wsfe", 0, WsaaCallResult.CACHED)
        entry = _capture_log_json(wsaa_log_records)
        assert entry["result"] == "cached"

    def test_retried_result(self, wsaa_log_records):
        log_wsaa_call("20123456789", "wsfe", 450, WsaaCallResult.RETRIED)
        entry = _capture_log_json(wsaa_log_records)
        assert entry["result"] == "retried"

    def test_failed_result_includes_error_cause(self, wsaa_log_records):
        log_wsaa_call("20111111111", "wsfe", 300, WsaaCallResult.FAILED, error_cause="wsaa_unreachable")
        entry = _capture_log_json(wsaa_log_records)
        assert entry["result"] == "failed"
        assert entry["error_cause"] == "wsaa_unreachable"

    def test_latency_ms_is_int(self, wsaa_log_records):
        log_wsaa_call("20123456789", "wsfe", 99, WsaaCallResult.OK)
        entry = _capture_log_json(wsaa_log_records)
        assert isinstance(entry["latency_ms"], int)

    def test_ts_is_iso8601(self, wsaa_log_records):
        from datetime import datetime
        log_wsaa_call("20123456789", "wsfe", 10, WsaaCallResult.OK)
        entry = _capture_log_json(wsaa_log_records)
        parsed = datetime.fromisoformat(entry["ts"])
        assert parsed.tzinfo is not None
