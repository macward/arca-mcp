"""Integration tests for the full HITL invoicing flow: draft → validate → confirm.

These tests exercise the complete MCP tool layer (invoicing.py) including
DraftStore, policy validation, and the WSFE client — with the WSFE calls mocked.

Guard: set ARCA_INTEGRATION_TESTS=1 to run.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from arca_mcp.config.resolver import RuntimeConfig
from arca_mcp.config_settings import Environment
from arca_mcp.errors import ArcaErrorCause
from arca_mcp.invoicing.draft_store import DraftStore
from arca_mcp.invoicing.idempotency import IdempotencyStore
from arca_mcp.mcp import invoicing as _invoicing_mod
from arca_mcp.wsaa.models import SetupCheckResult, WsaaToken
from arca_mcp.wsfe.models import FECAESolicitarResponse, FECompUltimoAutorizadoResponse

# ---------------------------------------------------------------------------
# Opt-in guard
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.skipif(
    os.environ.get("ARCA_INTEGRATION_TESTS") != "1",
    reason="Set ARCA_INTEGRATION_TESTS=1 to run",
)

# ---------------------------------------------------------------------------
# Helpers to extract underlying async functions from FastMCP tool wrappers
# ---------------------------------------------------------------------------


def _tool_fn(tool):
    """FastMCP may wrap tools in a FunctionTool object; extract the raw fn."""
    return getattr(tool, "fn", tool)


create_voucher_draft = _tool_fn(_invoicing_mod.create_voucher_draft)
validate_voucher_draft = _tool_fn(_invoicing_mod.validate_voucher_draft)
confirm_voucher_creation = _tool_fn(_invoicing_mod.confirm_voucher_creation)
get_last_voucher_number = _tool_fn(_invoicing_mod.get_last_voucher_number)

# ---------------------------------------------------------------------------
# Test fixtures and helpers
# ---------------------------------------------------------------------------


def _ok_wsaa_result() -> SetupCheckResult:
    return SetupCheckResult(
        ok=True,
        token=WsaaToken(
            token="test-token",
            sign="test-sign",
            generation_time="2026-01-01T00:00:00",
            expiration_time="2026-01-01T12:00:00",
        ),
    )


def _stub_runtime_config(tmp_path: Path) -> RuntimeConfig:
    cert_path = tmp_path / "cert.crt"
    key_path = tmp_path / "key.pem"
    cert_path.write_text("CERT")
    key_path.write_text("KEY")
    return RuntimeConfig(
        environment=Environment.HOMOLOGACION,
        cert_path=cert_path,
        key_path=key_path,
        emitter_cuit="20123456789",
    )


def _fake_cae_response() -> FECAESolicitarResponse:
    return FECAESolicitarResponse(
        cae="12345678901234",
        cbte_nro=42,
        cae_fch_vto="20260201",
        resultado="A",
        observaciones=[],
    )


def _fake_ultimo_autorizado_response() -> FECompUltimoAutorizadoResponse:
    return FECompUltimoAutorizadoResponse(cbte_nro=5)


@pytest.fixture(autouse=True)
def isolated_stores():
    """Replace module-level DraftStore and IdempotencyStore with fresh instances per test."""
    fresh_draft_store = DraftStore()
    fresh_idempotency_store = IdempotencyStore()
    with (
        patch.object(_invoicing_mod, "_draft_store", fresh_draft_store),
        patch.object(_invoicing_mod, "_idempotency_store", fresh_idempotency_store),
    ):
        yield fresh_draft_store, fresh_idempotency_store


# ---------------------------------------------------------------------------
# Scenario 1: Full flow Factura B in homologación
# ---------------------------------------------------------------------------


class TestFullFlowFacturaB:
    """create_voucher_draft → validate_voucher_draft → confirm_voucher_creation → CAE."""

    @pytest.mark.asyncio
    async def test_full_flow_returns_cae(self, tmp_path):
        config = _stub_runtime_config(tmp_path)

        with (
            patch("arca_mcp.mcp.invoicing.resolve_runtime_config", return_value=config),
            patch(
                "arca_mcp.mcp.invoicing.validate_wsaa_login",
                new=AsyncMock(return_value=_ok_wsaa_result()),
            ),
            patch(
                "arca_mcp.mcp.invoicing.wsfe_client.fecae_solicitar",
                return_value=_fake_cae_response(),
            ),
        ):
            # Step 1: Create draft
            draft_result = await create_voucher_draft(
                cbte_tipo=6,
                punto_venta=1,
                fecha_cbte="20260115",
                cuit_receptor="20111111112",
                doc_tipo=80,
                imp_neto="1000.00",
                alicuota_id="5",
            )
            assert "draft_id" in draft_result, f"Expected draft_id, got: {draft_result}"
            assert draft_result["status"] == "PENDING"
            draft_id = draft_result["draft_id"]

            # Step 2: Validate
            validate_result = await validate_voucher_draft(draft_id=draft_id)
            assert validate_result["is_valid"] is True, f"Validation failed: {validate_result}"
            assert validate_result["status"] == "VALIDATED"

            # Step 3: Confirm
            confirm_result = await confirm_voucher_creation(
                draft_id=draft_id,
                idempotency_key="test-idem-key-001",
            )
            assert "cae" in confirm_result, f"Expected cae in result, got: {confirm_result}"
            assert confirm_result["cae"] == "12345678901234"
            assert confirm_result["cbte_nro"] == 42
            assert confirm_result["cae_fch_vto"] == "20260201"
            assert confirm_result["draft_id"] == draft_id
            assert confirm_result["idempotency_key"] == "test-idem-key-001"


# ---------------------------------------------------------------------------
# Scenario 2: Confirm without prior validate → DRAFT_NOT_VALIDATED
# ---------------------------------------------------------------------------


class TestConfirmWithoutValidate:
    """Attempting to confirm a PENDING draft must return DRAFT_NOT_VALIDATED error."""

    @pytest.mark.asyncio
    async def test_confirm_pending_draft_returns_error(self, tmp_path):
        config = _stub_runtime_config(tmp_path)

        with patch("arca_mcp.mcp.invoicing.resolve_runtime_config", return_value=config):
            # Create draft (no validate step)
            draft_result = await create_voucher_draft(
                cbte_tipo=6,
                punto_venta=1,
                fecha_cbte="20260115",
                cuit_receptor="20111111112",
                doc_tipo=80,
                imp_neto="500.00",
                alicuota_id="5",
            )
            draft_id = draft_result["draft_id"]

            # Confirm directly — should fail
            confirm_result = await confirm_voucher_creation(
                draft_id=draft_id,
                idempotency_key="test-idem-key-002",
            )

        assert "error" in confirm_result, f"Expected error, got: {confirm_result}"
        assert confirm_result["error"]["cause"] == "DRAFT_NOT_VALIDATED"


# ---------------------------------------------------------------------------
# Scenario 3: Double confirm same idempotency_key → identical result, no second WSFE call
# ---------------------------------------------------------------------------


class TestDoubleConfirmIdempotency:
    """Second confirm with same idempotency_key returns cached result without a second WSFE call."""

    @pytest.mark.asyncio
    async def test_double_confirm_returns_same_result(self, tmp_path):
        config = _stub_runtime_config(tmp_path)
        wsfe_call_count = {"n": 0}

        def counting_fecae_solicitar(**kwargs):
            wsfe_call_count["n"] += 1
            return _fake_cae_response()

        with (
            patch("arca_mcp.mcp.invoicing.resolve_runtime_config", return_value=config),
            patch(
                "arca_mcp.mcp.invoicing.validate_wsaa_login",
                new=AsyncMock(return_value=_ok_wsaa_result()),
            ),
            patch(
                "arca_mcp.mcp.invoicing.wsfe_client.fecae_solicitar",
                side_effect=counting_fecae_solicitar,
            ),
        ):
            # Full flow
            draft_result = await create_voucher_draft(
                cbte_tipo=6,
                punto_venta=1,
                fecha_cbte="20260115",
                cuit_receptor="20111111112",
                doc_tipo=80,
                imp_neto="1000.00",
                alicuota_id="5",
            )
            draft_id = draft_result["draft_id"]

            await validate_voucher_draft(draft_id=draft_id)

            idem_key = "test-idem-key-003"

            first_result = await confirm_voucher_creation(
                draft_id=draft_id,
                idempotency_key=idem_key,
            )
            second_result = await confirm_voucher_creation(
                draft_id=draft_id,
                idempotency_key=idem_key,
            )

        # WSFE must only have been called once
        assert wsfe_call_count["n"] == 1, (
            f"fecae_solicitar called {wsfe_call_count['n']} times; expected 1"
        )
        # Both calls return identical result
        assert first_result == second_result
        assert first_result["cae"] == "12345678901234"


# ---------------------------------------------------------------------------
# Scenario 4: Validate with invalid alícuota → is_valid=False
# ---------------------------------------------------------------------------


class TestValidateInvalidAlicuota:
    """Draft with unknown alicuota_id is rejected at creation time by Pydantic validation.

    VoucherDraft enforces a known set of alicuota IDs as part of its model.
    create_voucher_draft therefore returns an INVALID_CATALOG_VALUE error immediately
    rather than creating a draft that later fails at validate time.
    """

    @pytest.mark.asyncio
    async def test_invalid_alicuota_rejected_at_create(self):
        result = await create_voucher_draft(
            cbte_tipo=6,
            punto_venta=1,
            fecha_cbte="20260115",
            cuit_receptor="20111111112",
            doc_tipo=80,
            imp_neto="1000.00",
            alicuota_id="999",  # not in IVA_ALIQUOTS catalog
        )
        # create_voucher_draft returns an ArcaError (not a dict) when Pydantic rejects the model
        from arca_mcp.errors import ArcaError

        assert isinstance(result, ArcaError), f"Expected ArcaError, got: {result}"
        assert result.cause == ArcaErrorCause.INVALID_CATALOG_VALUE
        assert "999" in result.message

    @pytest.mark.asyncio
    async def test_validate_draft_with_invalid_alicuota_via_store(self, isolated_stores):
        """If a draft with an invalid alicuota somehow reaches the store, validate rejects it."""
        from arca_mcp.invoicing.models import DraftStatus, VoucherDraft
        from decimal import Decimal
        from datetime import datetime, timezone
        import uuid

        draft_store, _ = isolated_stores

        # Bypass create_voucher_draft and inject directly into the store
        # using model_construct to skip Pydantic validation
        bad_draft = VoucherDraft.model_construct(
            draft_id=str(uuid.uuid4()),
            cbte_tipo=6,
            punto_venta=1,
            fecha_cbte="20260115",
            cuit_receptor="20111111112",
            doc_tipo=80,
            imp_neto=Decimal("1000.00"),
            imp_iva=Decimal("210.00"),
            imp_total=Decimal("1210.00"),
            alicuota_id="999",
            status=DraftStatus.PENDING,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        await draft_store.create(bad_draft)

        validate_result = await validate_voucher_draft(draft_id=bad_draft.draft_id)

        assert validate_result["is_valid"] is False
        assert validate_result["status"] == "PENDING"
        error_codes = [e["code"] for e in validate_result["errors"]]
        assert "UNKNOWN_ALICUOTA" in error_codes, (
            f"Expected UNKNOWN_ALICUOTA in errors, got: {error_codes}"
        )


# ---------------------------------------------------------------------------
# Scenario 5: get_last_voucher_number → int >= 0 (mocked WSFE)
# ---------------------------------------------------------------------------


class TestGetLastVoucherNumber:
    """get_last_voucher_number returns cbte_nro as an integer >= 0."""

    @pytest.mark.asyncio
    async def test_returns_cbte_nro(self, tmp_path):
        config = _stub_runtime_config(tmp_path)

        with (
            patch("arca_mcp.mcp.invoicing.resolve_runtime_config", return_value=config),
            patch(
                "arca_mcp.mcp.invoicing.validate_wsaa_login",
                new=AsyncMock(return_value=_ok_wsaa_result()),
            ),
            patch(
                "arca_mcp.mcp.invoicing.wsfe_client.fecomp_ultimo_autorizado",
                return_value=_fake_ultimo_autorizado_response(),
            ),
        ):
            result = await get_last_voucher_number(punto_venta=1, cbte_tipo=6)

        assert "cbte_nro" in result, f"Expected cbte_nro, got: {result}"
        assert isinstance(result["cbte_nro"], int)
        assert result["cbte_nro"] >= 0
        assert result["cbte_nro"] == 5
