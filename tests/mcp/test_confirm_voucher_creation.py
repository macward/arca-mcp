"""Tests del camino crítico de emisión: confirm_voucher_creation y sus helpers.

Cubre `confirm_voucher_creation`, `_invoke_wsfe` y `_persist_emission` — el flujo
irreversible que solicita el CAE a WSFEv1. Todo se ejerce con dobles manuales
(sin librerías de mocking) y sin acceso a red: el cliente WSFE, el login WSAA y
el resolver de configuración se reemplazan por funciones locales vía monkeypatch.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from arca_mcp.audit.emission_log import AuditLog
from arca_mcp.config.resolver import RuntimeConfig
from arca_mcp.config.settings import Environment
from arca_mcp.errors import ArcaError, ArcaErrorCause
from arca_mcp.invoicing.draft_store import DraftStore
from arca_mcp.invoicing.idempotency import IdempotencyStore
from arca_mcp.invoicing.models import DraftStatus, VoucherDraft
from arca_mcp.mcp import invoicing as _invoicing_mod
from arca_mcp.wsfe import client as wsfe_client
from arca_mcp.wsfe.models import FECAESolicitarResponse


def _tool_fn(tool):
    return getattr(tool, "fn", tool)


confirm_voucher_creation = _tool_fn(_invoicing_mod.confirm_voucher_creation)


# ---------------------------------------------------------------------------
# Dobles manuales
# ---------------------------------------------------------------------------


class RecordingAuditLog:
    """Audit log en memoria; opcionalmente falla en los eventos indicados."""

    def __init__(self, fail_on: set[str] | None = None) -> None:
        self.entries: list[dict] = []
        self._fail_on = fail_on or set()

    async def append(self, entry: dict) -> None:
        if entry.get("event") in self._fail_on:
            raise OSError(f"audit log no disponible para {entry.get('event')}")
        self.entries.append(entry)

    @property
    def events(self) -> list[str]:
        return [e["event"] for e in self.entries]


class BrokenIdempotencyStore:
    """Store cuyo `set_done` falla, simulando SQLite roto tras obtener el CAE."""

    def __init__(self, inner: IdempotencyStore) -> None:
        self._inner = inner
        self.deleted: list[str] = []

    async def set_pending(self, key: str) -> bool:
        return await self._inner.set_pending(key)

    async def get(self, key: str):
        return await self._inner.get(key)

    async def set_done(self, key: str, result: dict) -> None:
        raise RuntimeError("disco lleno")

    async def delete(self, key: str) -> None:
        self.deleted.append(key)
        await self._inner.delete(key)


class WsfeSpy:
    """Reemplazo de `wsfe_client.fecae_solicitar`.

    Registra las llamadas recibidas y devuelve (o lanza) lo que se le configure.
    """

    def __init__(self, outcome) -> None:
        self._outcome = outcome
        self.calls: list[dict] = []

    def __call__(self, *, token: str, sign: str, environment: str, request) -> object:
        self.calls.append(
            {"token": token, "sign": sign, "environment": environment, "request": request}
        )
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _approved_response(cbte_nro: int = 42) -> FECAESolicitarResponse:
    return FECAESolicitarResponse(
        cae="71234567890123",
        cbte_nro=cbte_nro,
        cae_fch_vto="20260810",
        resultado="A",
        observaciones=[],
    )


def _draft(
    draft_id: str = "draft-1",
    status: DraftStatus = DraftStatus.VALIDATED,
) -> VoucherDraft:
    now = datetime.now(timezone.utc)
    return VoucherDraft(
        draft_id=draft_id,
        status=status,
        cbte_tipo=6,
        punto_venta=3,
        fecha_cbte="20260101",
        cuit_receptor="20111111112",
        doc_tipo=80,
        imp_neto=Decimal("1000.00"),
        alicuota_id="5",
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def stores(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Aísla draft store, idempotency store y audit log del módulo MCP."""
    draft_store = DraftStore(db_path=tmp_path / "drafts.db")
    idempotency_store = IdempotencyStore(db_path=tmp_path / "idempotency.db")
    audit_log = RecordingAuditLog()

    monkeypatch.setattr(_invoicing_mod, "_draft_store", draft_store)
    monkeypatch.setattr(_invoicing_mod, "_idempotency_store", idempotency_store)
    monkeypatch.setattr(_invoicing_mod, "_audit_log", audit_log)

    yield draft_store, idempotency_store, audit_log

    idempotency_store.close()
    draft_store.close()


@pytest.fixture
def happy_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Config resuelta y token WSAA válidos, sin tocar disco real ni red."""
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
        return ("TOKEN-abc", "SIGN-xyz")

    monkeypatch.setattr(_invoicing_mod, "_get_wsaa_token", _token)
    return config


def _install_wsfe(monkeypatch: pytest.MonkeyPatch, outcome) -> WsfeSpy:
    spy = WsfeSpy(outcome)
    monkeypatch.setattr(wsfe_client, "fecae_solicitar", spy)
    return spy


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


async def test_confirm_happy_path_returns_cae(stores, happy_config, monkeypatch):
    draft_store, idempotency_store, audit_log = stores
    await draft_store.create(_draft())
    spy = _install_wsfe(monkeypatch, _approved_response(cbte_nro=77))

    result = await confirm_voucher_creation("draft-1", "idem-1")

    assert result == {
        "cae": "71234567890123",
        "cbte_nro": 77,
        "cae_fch_vto": "20260810",
        "draft_id": "draft-1",
        "idempotency_key": "idem-1",
    }
    assert len(spy.calls) == 1


async def test_confirm_happy_path_persists_state(stores, happy_config, monkeypatch):
    draft_store, idempotency_store, audit_log = stores
    await draft_store.create(_draft())
    _install_wsfe(monkeypatch, _approved_response())

    await confirm_voucher_creation("draft-1", "idem-1")

    stored = await draft_store.get("draft-1")
    assert stored is not None and stored.status == DraftStatus.CONFIRMED

    entry = await idempotency_store.get("idem-1")
    assert entry is not None
    status, cached = entry
    assert status == "DONE"
    assert cached is not None and cached["cae"] == "71234567890123"


async def test_confirm_writes_wal_before_confirmation(stores, happy_config, monkeypatch):
    """El WAL (PENDING_CAE) se escribe antes de llamar a WSFE; CAE_CONFIRMED después."""
    draft_store, _, audit_log = stores
    await draft_store.create(_draft())
    _install_wsfe(monkeypatch, _approved_response())

    await confirm_voucher_creation("draft-1", "idem-1")

    assert audit_log.events == ["PENDING_CAE", "CAE_CONFIRMED"]
    wal = audit_log.entries[0]
    assert wal["draft_id"] == "draft-1"
    assert wal["idempotency_key"] == "idem-1"
    assert wal["cuit"] == "20111111112"
    assert wal["imp_total"] == "1210.00"


async def test_wal_entry_precedes_wsfe_call(stores, happy_config, monkeypatch):
    """Verifica el orden real: al entrar a fecae_solicitar el WAL ya está escrito."""
    draft_store, _, audit_log = stores
    await draft_store.create(_draft())

    observed: list[list[str]] = []

    def _fecae(*, token, sign, environment, request):
        observed.append(list(audit_log.events))
        return _approved_response()

    monkeypatch.setattr(wsfe_client, "fecae_solicitar", _fecae)

    await confirm_voucher_creation("draft-1", "idem-1")

    assert observed == [["PENDING_CAE"]]


async def test_fecae_request_carries_draft_amounts(stores, happy_config, monkeypatch):
    draft_store, _, _ = stores
    await draft_store.create(_draft())
    spy = _install_wsfe(monkeypatch, _approved_response())

    await confirm_voucher_creation("draft-1", "idem-1")

    call = spy.calls[0]
    assert call["token"] == "TOKEN-abc"
    assert call["sign"] == "SIGN-xyz"
    assert call["environment"] == Environment.HOMOLOGACION
    request = call["request"]
    assert request.cuit == "20111111112"
    assert request.punto_venta == 3
    assert request.cbte_tipo == 6
    assert request.imp_neto == Decimal("1000.00")
    assert request.imp_iva == Decimal("210.00")
    assert request.imp_total == Decimal("1210.00")


# ---------------------------------------------------------------------------
# Idempotencia
# ---------------------------------------------------------------------------


async def test_done_key_returns_cached_result_without_calling_wsfe(
    stores, happy_config, monkeypatch
):
    draft_store, idempotency_store, _ = stores
    await draft_store.create(_draft())
    cached = {"cae": "99999999999999", "cbte_nro": 5}
    await idempotency_store.set_pending("idem-1")
    await idempotency_store.set_done("idem-1", cached)
    spy = _install_wsfe(monkeypatch, _approved_response())

    result = await confirm_voucher_creation("draft-1", "idem-1")

    assert result == cached
    assert spy.calls == [], "una clave DONE no debe volver a pegarle a WSFE"


async def test_pending_key_returns_in_progress_error(stores, happy_config, monkeypatch):
    draft_store, idempotency_store, _ = stores
    await draft_store.create(_draft())
    await idempotency_store.set_pending("idem-1")
    spy = _install_wsfe(monkeypatch, _approved_response())

    result = await confirm_voucher_creation("draft-1", "idem-1")

    assert result["error"]["cause"] == "EMISSION_IN_PROGRESS"
    assert spy.calls == []


async def test_done_key_without_result_returns_empty_dict(stores, happy_config):
    """Fila DONE con result_json NULL — degrada a {} sin reventar.

    Se inserta por SQL directo a propósito: la API pública no puede producir esta
    forma de fila (`set_done` siempre serializa un dict). Es un estado que sólo
    aparece por corrupción o por una migración vieja, y el código lo tolera.
    """
    _, idempotency_store, _ = stores
    idempotency_store._conn.execute(
        "INSERT INTO entries(key, status, result_json, created_at) "
        "VALUES ('idem-1', 'DONE', NULL, '2026-01-01T00:00:00+00:00')"
    )
    idempotency_store._conn.commit()

    assert await confirm_voucher_creation("draft-1", "idem-1") == {}


async def test_lost_claim_race_returns_in_progress_error(stores, happy_config, monkeypatch):
    """Otro proceso reclamó la clave entre el `get` y el `set_pending`."""
    draft_store, idempotency_store, _ = stores
    await draft_store.create(_draft())

    class LosingStore:
        async def get(self, key: str):
            return None

        async def set_pending(self, key: str) -> bool:
            return False

    monkeypatch.setattr(_invoicing_mod, "_idempotency_store", LosingStore())
    spy = _install_wsfe(monkeypatch, _approved_response())

    result = await confirm_voucher_creation("draft-1", "idem-1")

    assert result["error"]["cause"] == "EMISSION_IN_PROGRESS"
    assert spy.calls == []


async def test_in_progress_error_is_a_fresh_copy():
    """Mutar la respuesta no debe contaminar la constante del módulo."""
    first = _invoicing_mod._in_progress_error()
    first["error"]["cause"] = "MUTADO"

    second = _invoicing_mod._in_progress_error()
    assert second["error"]["cause"] == "EMISSION_IN_PROGRESS"
    assert _invoicing_mod._IN_PROGRESS_ERROR["error"]["cause"] == "EMISSION_IN_PROGRESS"


# ---------------------------------------------------------------------------
# Estados de draft inválidos
# ---------------------------------------------------------------------------


async def test_missing_draft_releases_idempotency_key(stores, happy_config, monkeypatch):
    _, idempotency_store, audit_log = stores
    spy = _install_wsfe(monkeypatch, _approved_response())

    result = await confirm_voucher_creation("no-existe", "idem-1")

    assert result["error"]["cause"] == "DRAFT_NOT_FOUND"
    assert await idempotency_store.get("idem-1") is None, "la clave debe liberarse"
    assert spy.calls == []
    assert audit_log.events == []


@pytest.mark.parametrize(
    "status", [DraftStatus.PENDING, DraftStatus.CONFIRMED, DraftStatus.REJECTED]
)
async def test_non_validated_draft_is_rejected(
    stores, happy_config, monkeypatch, status
):
    draft_store, idempotency_store, _ = stores
    await draft_store.create(_draft(status=status))
    spy = _install_wsfe(monkeypatch, _approved_response())

    result = await confirm_voucher_creation("draft-1", "idem-1")

    assert result["error"]["cause"] == "DRAFT_NOT_VALIDATED"
    assert status.value in result["error"]["message"]
    assert await idempotency_store.get("idem-1") is None
    assert spy.calls == []


# ---------------------------------------------------------------------------
# Fallos de configuración / WSAA
# ---------------------------------------------------------------------------


async def test_config_error_propagates_and_releases_key(stores, monkeypatch):
    draft_store, idempotency_store, _ = stores
    await draft_store.create(_draft())
    error = ArcaError(cause=ArcaErrorCause.MISSING_CONFIG, message="falta ARCA_CERT_PATH")
    monkeypatch.setattr(_invoicing_mod, "resolve_runtime_config", lambda: error)
    spy = _install_wsfe(monkeypatch, _approved_response())

    result = await confirm_voucher_creation("draft-1", "idem-1")

    assert result["error"]["cause"] == ArcaErrorCause.MISSING_CONFIG
    assert await idempotency_store.get("idem-1") is None
    assert spy.calls == []


async def test_missing_emitter_cuit_releases_key(stores, monkeypatch, tmp_path):
    draft_store, idempotency_store, _ = stores
    await draft_store.create(_draft())
    cert_path = tmp_path / "cert.crt"
    key_path = tmp_path / "key.pem"
    cert_path.write_bytes(b"cert")
    key_path.write_bytes(b"key")
    config = RuntimeConfig(
        environment=Environment.HOMOLOGACION,
        cert_path=cert_path,
        key_path=key_path,
        emitter_cuit=None,
    )
    monkeypatch.setattr(_invoicing_mod, "resolve_runtime_config", lambda: config)
    spy = _install_wsfe(monkeypatch, _approved_response())

    result = await confirm_voucher_creation("draft-1", "idem-1")

    assert result["error"]["cause"] == ArcaErrorCause.MISSING_CONFIG
    assert await idempotency_store.get("idem-1") is None
    assert spy.calls == []


async def test_wsaa_failure_releases_key(stores, happy_config, monkeypatch):
    draft_store, idempotency_store, audit_log = stores
    await draft_store.create(_draft())

    async def _failing_token(cert_path, key_path, environment, service, cuit=None):
        return ArcaError(
            cause=ArcaErrorCause.WSAA_AUTH_FAILED, message="certificado revocado"
        )

    monkeypatch.setattr(_invoicing_mod, "_get_wsaa_token", _failing_token)
    spy = _install_wsfe(monkeypatch, _approved_response())

    result = await confirm_voucher_creation("draft-1", "idem-1")

    assert result["error"]["cause"] == ArcaErrorCause.WSAA_AUTH_FAILED
    assert await idempotency_store.get("idem-1") is None
    assert spy.calls == []
    assert audit_log.events == [], "sin token no se escribe WAL"


# ---------------------------------------------------------------------------
# Fallos de WSFE
# ---------------------------------------------------------------------------


async def test_wsfe_arca_error_releases_key(stores, happy_config, monkeypatch):
    draft_store, idempotency_store, audit_log = stores
    await draft_store.create(_draft())
    _install_wsfe(
        monkeypatch,
        ArcaError(
            cause=ArcaErrorCause.ARCA_SERVICE_ERROR, message="WSFE devolvió fault SOAP"
        ),
    )

    result = await confirm_voucher_creation("draft-1", "idem-1")

    assert result["error"]["cause"] == ArcaErrorCause.ARCA_SERVICE_ERROR
    assert await idempotency_store.get("idem-1") is None
    assert audit_log.events == ["PENDING_CAE"], "el WAL queda como rastro del intento"
    stored = await draft_store.get("draft-1")
    assert stored is not None and stored.status == DraftStatus.VALIDATED


async def test_wsfe_rejection_reports_observaciones(stores, happy_config, monkeypatch):
    draft_store, idempotency_store, _ = stores
    await draft_store.create(_draft())
    _install_wsfe(
        monkeypatch,
        FECAESolicitarResponse(
            cae="",
            cbte_nro=0,
            cae_fch_vto="20260810",
            resultado="R",
            observaciones=["10016: fecha inválida", "10048: CUIT no habilitado"],
        ),
    )

    result = await confirm_voucher_creation("draft-1", "idem-1")

    assert result["error"]["cause"] == "WSFE_REJECTED"
    assert "10016: fecha inválida; 10048: CUIT no habilitado" in result["error"]["message"]
    assert await idempotency_store.get("idem-1") is None


async def test_wsfe_rejection_without_observaciones(stores, happy_config, monkeypatch):
    draft_store, _, _ = stores
    await draft_store.create(_draft())
    _install_wsfe(
        monkeypatch,
        FECAESolicitarResponse(
            cae="",
            cbte_nro=0,
            cae_fch_vto="20260810",
            resultado="R",
            observaciones=[],
        ),
    )

    result = await confirm_voucher_creation("draft-1", "idem-1")

    assert result["error"]["cause"] == "WSFE_REJECTED"
    assert "sin observaciones" in result["error"]["message"]


async def test_wsfe_exception_releases_key_and_reraises(stores, happy_config, monkeypatch):
    """Fallo transitorio: la excepción sube y el sentinel se borra para permitir retry."""
    draft_store, idempotency_store, _ = stores
    await draft_store.create(_draft())
    _install_wsfe(monkeypatch, TimeoutError("WSFE no respondió"))

    with pytest.raises(TimeoutError):
        await confirm_voucher_creation("draft-1", "idem-1")

    assert await idempotency_store.get("idem-1") is None


# ---------------------------------------------------------------------------
# Fallos de persistencia y del audit log
# ---------------------------------------------------------------------------


async def test_set_done_failure_preserves_cae_in_audit_log(
    stores, happy_config, monkeypatch
):
    """Si `set_done` falla, el CAE ya otorgado se preserva en el audit log."""
    draft_store, idempotency_store, audit_log = stores
    await draft_store.create(_draft())
    broken = BrokenIdempotencyStore(idempotency_store)
    monkeypatch.setattr(_invoicing_mod, "_idempotency_store", broken)
    _install_wsfe(monkeypatch, _approved_response(cbte_nro=77))

    with pytest.raises(RuntimeError):
        await confirm_voucher_creation("draft-1", "idem-1")

    assert audit_log.events == ["PENDING_CAE", "CAE_PERSISTENCE_FAILED"]
    failed = audit_log.entries[-1]
    assert failed["cae"] == "71234567890123"
    assert failed["cbte_nro"] == 77
    assert failed["idempotency_key"] == "idem-1"
    assert "disco lleno" in failed["error"]


async def test_set_done_failure_keeps_idempotency_key_claimed(
    stores, happy_config, monkeypatch
):
    """La clave NO se borra: un retry debe frenar en EMISSION_IN_PROGRESS, no re-emitir."""
    draft_store, idempotency_store, _ = stores
    await draft_store.create(_draft())
    broken = BrokenIdempotencyStore(idempotency_store)
    monkeypatch.setattr(_invoicing_mod, "_idempotency_store", broken)
    _install_wsfe(monkeypatch, _approved_response())

    with pytest.raises(RuntimeError):
        await confirm_voucher_creation("draft-1", "idem-1")

    assert broken.deleted == [], "el sentinel debe sobrevivir para forzar investigación"
    entry = await idempotency_store.get("idem-1")
    assert entry is not None and entry[0] == "PENDING"

    # El retry no vuelve a pegarle a WSFE.
    monkeypatch.setattr(_invoicing_mod, "_idempotency_store", idempotency_store)
    spy = _install_wsfe(monkeypatch, _approved_response())
    retry = await confirm_voucher_creation("draft-1", "idem-1")
    assert retry["error"]["cause"] == "EMISSION_IN_PROGRESS"
    assert spy.calls == []


async def test_audit_failure_during_recovery_is_swallowed(
    stores, happy_config, monkeypatch
):
    """Si el audit log también falla, se propaga el error original de persistencia."""
    draft_store, idempotency_store, _ = stores
    await draft_store.create(_draft())
    audit_log = RecordingAuditLog(fail_on={"CAE_PERSISTENCE_FAILED"})
    monkeypatch.setattr(_invoicing_mod, "_audit_log", audit_log)
    broken = BrokenIdempotencyStore(idempotency_store)
    monkeypatch.setattr(_invoicing_mod, "_idempotency_store", broken)
    _install_wsfe(monkeypatch, _approved_response())

    with pytest.raises(RuntimeError, match="disco lleno"):
        await confirm_voucher_creation("draft-1", "idem-1")

    assert audit_log.events == ["PENDING_CAE"]


async def test_wal_audit_failure_aborts_before_wsfe(stores, happy_config, monkeypatch):
    """Si el WAL no se puede escribir, no se llama a WSFE — no hay emisión a ciegas."""
    draft_store, _, _ = stores
    await draft_store.create(_draft())
    monkeypatch.setattr(
        _invoicing_mod, "_audit_log", RecordingAuditLog(fail_on={"PENDING_CAE"})
    )
    spy = _install_wsfe(monkeypatch, _approved_response())

    with pytest.raises(OSError):
        await confirm_voucher_creation("draft-1", "idem-1")

    assert spy.calls == []


async def test_confirmation_audit_failure_propagates(stores, happy_config, monkeypatch):
    """Fallo del audit log final: sube el error, pero la idempotencia quedó DONE."""
    draft_store, idempotency_store, _ = stores
    await draft_store.create(_draft())
    monkeypatch.setattr(
        _invoicing_mod, "_audit_log", RecordingAuditLog(fail_on={"CAE_CONFIRMED"})
    )
    _install_wsfe(monkeypatch, _approved_response())

    with pytest.raises(OSError):
        await confirm_voucher_creation("draft-1", "idem-1")

    entry = await idempotency_store.get("idem-1")
    assert entry is not None and entry[0] == "DONE", (
        "con la clave en DONE un retry devuelve el CAE cacheado en lugar de re-emitir"
    )


# ---------------------------------------------------------------------------
# Audit log real (sin dobles) — verifica la integración con AuditLog
# ---------------------------------------------------------------------------


async def test_happy_path_with_real_audit_log(
    stores, happy_config, monkeypatch, tmp_path
):
    draft_store, _, _ = stores
    await draft_store.create(_draft())
    log_path = tmp_path / "audit" / "audit.jsonl"
    monkeypatch.setattr(_invoicing_mod, "_audit_log", AuditLog(log_path))
    _install_wsfe(monkeypatch, _approved_response())

    result = await confirm_voucher_creation("draft-1", "idem-1")

    assert result["cae"] == "71234567890123"
    lines = log_path.read_text().strip().splitlines()
    assert len(lines) == 2
    assert '"PENDING_CAE"' in lines[0]
    assert '"CAE_CONFIRMED"' in lines[1]
