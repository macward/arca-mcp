"""Tests del flujo HITL completo: create → validate → confirm.

Recorre las tres tools MCP en secuencia con el cliente WSFE reemplazado por un
doble manual, verificando que el draft avanza PENDING → VALIDATED → CONFIRMED y
que las transiciones inválidas se rechazan antes de tocar WSFE. Sin red.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from arca_mcp.config.resolver import RuntimeConfig
from arca_mcp.config.settings import Environment
from arca_mcp.errors import ArcaError, ArcaErrorCause
from arca_mcp.invoicing.draft_store import DraftStore
from arca_mcp.invoicing.idempotency import IdempotencyStore
from arca_mcp.invoicing.models import DraftStatus
from arca_mcp.mcp import invoicing as _invoicing_mod
from arca_mcp.wsfe import client as wsfe_client
from arca_mcp.wsfe.models import FECAESolicitarResponse


def _tool_fn(tool):
    return getattr(tool, "fn", tool)


create_voucher_draft = _tool_fn(_invoicing_mod.create_voucher_draft)
validate_voucher_draft = _tool_fn(_invoicing_mod.validate_voucher_draft)
confirm_voucher_creation = _tool_fn(_invoicing_mod.confirm_voucher_creation)


class SilentAuditLog:
    """Audit log en memoria — evita escribir en ~/.arca-mcp durante los tests."""

    def __init__(self) -> None:
        self.entries: list[dict] = []

    async def append(self, entry: dict) -> None:
        self.entries.append(entry)


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


@pytest.fixture
def wired(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Stores aislados + config/WSAA/WSFE resueltos con dobles manuales."""
    draft_store = DraftStore(db_path=tmp_path / "drafts.db")
    idempotency_store = IdempotencyStore(db_path=tmp_path / "idempotency.db")
    monkeypatch.setattr(_invoicing_mod, "_draft_store", draft_store)
    monkeypatch.setattr(_invoicing_mod, "_idempotency_store", idempotency_store)
    monkeypatch.setattr(_invoicing_mod, "_audit_log", SilentAuditLog())

    cert_path = tmp_path / "cert.crt"
    key_path = tmp_path / "key.pem"
    cert_path.write_bytes(b"cert")
    key_path.write_bytes(b"key")
    config = RuntimeConfig(
        environment=Environment.HOMOLOGACION,
        cert_path=cert_path,
        key_path=key_path,
        emitter_cuit="20111111112",
    )
    monkeypatch.setattr(_invoicing_mod, "resolve_runtime_config", lambda: config)

    async def _token(cert_path, key_path, environment, service, cuit=None):
        return ("TOKEN", "SIGN")

    monkeypatch.setattr(_invoicing_mod, "_get_wsaa_token", _token)

    calls: list[object] = []

    def _fecae(*, token, sign, environment, request):
        calls.append(request)
        return FECAESolicitarResponse(
            cae="71234567890123",
            cbte_nro=len(calls),
            cae_fch_vto="20991231",
            resultado="A",
            observaciones=[],
        )

    monkeypatch.setattr(wsfe_client, "fecae_solicitar", _fecae)

    yield draft_store, calls

    idempotency_store.close()
    draft_store.close()


async def _new_draft(**overrides) -> dict:
    kwargs = {
        "cbte_tipo": 6,
        "punto_venta": 3,
        "fecha_cbte": _today(),
        "cuit_receptor": "20111111112",
        "doc_tipo": 80,
        "imp_neto": "1000.00",
        "alicuota_id": "5",
    }
    kwargs.update(overrides)
    return await create_voucher_draft(**kwargs)


# ---------------------------------------------------------------------------
# create_voucher_draft
# ---------------------------------------------------------------------------


async def test_create_draft_returns_computed_amounts(wired):
    created = await _new_draft()

    assert created["status"] == DraftStatus.PENDING
    assert created["imp_neto"] == "1000.00"
    assert created["imp_iva"] == "210.00"
    assert created["imp_total"] == "1210.00"
    assert created["draft_id"]
    assert created["created_at"]


async def test_create_draft_persists_in_store(wired):
    draft_store, _ = wired
    created = await _new_draft()

    stored = await draft_store.get(created["draft_id"])
    assert stored is not None
    assert stored.status == DraftStatus.PENDING
    assert stored.imp_neto == Decimal("1000.00")


async def test_create_draft_rejects_non_numeric_imp_neto(wired):
    result = await _new_draft(imp_neto="mil pesos")

    assert isinstance(result, ArcaError)
    assert result.cause == ArcaErrorCause.INVALID_CATALOG_VALUE
    assert "imp_neto" in result.message


async def test_create_draft_rejects_invalid_model(wired):
    """doc_tipo=99 exige cuit_receptor='0' — la validación Pydantic se traduce a ArcaError."""
    result = await _new_draft(doc_tipo=99, cuit_receptor="20111111112")

    assert isinstance(result, ArcaError)
    assert result.cause == ArcaErrorCause.INVALID_CATALOG_VALUE


# ---------------------------------------------------------------------------
# validate_voucher_draft
# ---------------------------------------------------------------------------


async def test_validate_promotes_draft_to_validated(wired):
    draft_store, _ = wired
    created = await _new_draft()

    result = await validate_voucher_draft(created["draft_id"])

    assert result["is_valid"] is True
    assert result["status"] == DraftStatus.VALIDATED.value
    assert result["errors"] == []
    stored = await draft_store.get(created["draft_id"])
    assert stored is not None and stored.status == DraftStatus.VALIDATED


async def test_validate_reports_policy_errors_and_keeps_pending(wired):
    draft_store, _ = wired
    far_future = (datetime.now(timezone.utc) + timedelta(days=90)).strftime("%Y%m%d")
    created = await _new_draft(fecha_cbte=far_future)

    result = await validate_voucher_draft(created["draft_id"])

    assert result["is_valid"] is False
    assert result["status"] == DraftStatus.PENDING.value
    assert any(e["field"] == "fecha_cbte" for e in result["errors"])
    stored = await draft_store.get(created["draft_id"])
    assert stored is not None and stored.status == DraftStatus.PENDING


async def test_validate_unknown_draft_returns_not_found(wired):
    result = await validate_voucher_draft("no-existe")

    assert result["error"]["cause"] == "DRAFT_NOT_FOUND"


async def test_validate_requires_pending_status(wired):
    created = await _new_draft()
    await validate_voucher_draft(created["draft_id"])

    result = await validate_voucher_draft(created["draft_id"])

    assert result["error"]["cause"] == "DRAFT_INVALID_STATUS"
    assert DraftStatus.VALIDATED.value in result["error"]["message"]


async def test_validate_store_failure_becomes_internal_error(wired, monkeypatch):
    class FailingStore:
        async def get(self, draft_id: str):
            raise RuntimeError("db bloqueada")

    monkeypatch.setattr(_invoicing_mod, "_draft_store", FailingStore())

    result = await validate_voucher_draft("cualquiera")

    assert result["error"]["cause"] == "INTERNAL_ERROR"
    assert "db bloqueada" in result["error"]["message"]


# ---------------------------------------------------------------------------
# Flujo completo
# ---------------------------------------------------------------------------


async def test_full_hitl_flow_emits_once(wired):
    draft_store, calls = wired

    created = await _new_draft()
    validated = await validate_voucher_draft(created["draft_id"])
    assert validated["is_valid"] is True

    confirmed = await confirm_voucher_creation(created["draft_id"], "idem-flow")

    assert confirmed["cae"] == "71234567890123"
    assert confirmed["draft_id"] == created["draft_id"]
    stored = await draft_store.get(created["draft_id"])
    assert stored is not None and stored.status == DraftStatus.CONFIRMED
    assert len(calls) == 1


async def test_confirm_without_validating_does_not_call_wsfe(wired):
    _, calls = wired
    created = await _new_draft()

    result = await confirm_voucher_creation(created["draft_id"], "idem-flow")

    assert result["error"]["cause"] == "DRAFT_NOT_VALIDATED"
    assert calls == []


async def test_repeated_confirm_with_same_key_emits_once(wired):
    _, calls = wired
    created = await _new_draft()
    await validate_voucher_draft(created["draft_id"])

    first = await confirm_voucher_creation(created["draft_id"], "idem-flow")
    second = await confirm_voucher_creation(created["draft_id"], "idem-flow")

    assert first == second
    assert len(calls) == 1, "el segundo confirm debe servirse del cache de idempotencia"
