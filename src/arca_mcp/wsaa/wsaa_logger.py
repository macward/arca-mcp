"""Structured JSON logging for WSAA calls.

Emits one log entry per WSAA operation with observability metadata.
Fields: ts, cuit, service, latency_ms, result, error_cause (optional).
"""

import datetime
import json
import logging
from enum import StrEnum


class WsaaCallResult(StrEnum):
    OK = "ok"
    CACHED = "cached"
    RETRIED = "retried"
    FAILED = "failed"


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return record.getMessage()


def _build_logger() -> logging.Logger:
    log = logging.getLogger("arca_mcp.wsaa.calls")
    if not log.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(_JsonFormatter())
        log.addHandler(handler)
        log.setLevel(logging.INFO)
    return log


_logger = _build_logger()


def log_wsaa_call(
    cuit: str,
    service: str,
    latency_ms: int,
    result: WsaaCallResult | str,
    error_cause: str | None = None,
) -> None:
    """Emit a structured JSON log entry for a WSAA call."""
    payload: dict = {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "cuit": cuit,
        "service": service,
        "latency_ms": int(latency_ms),
        "result": str(result),
    }
    if error_cause is not None:
        payload["error_cause"] = error_cause
    _logger.info(json.dumps(payload))
