"""E2E tests de la Lookup Layer contra servicios reales de homologación ARCA.

Requieren env vars:
- ARCA_TEST_CERT_PATH: path al .crt de homologación
- ARCA_TEST_KEY_PATH:  path al .key RSA (sin password)
- ARCA_TEST_CUIT:      CUIT del titular del certificado (para consultas de padrón)

Si las env vars no están seteadas, todos los tests skipean automáticamente.

Para correrlos:
    ARCA_TEST_CERT_PATH=/path/to/test.crt \\
    ARCA_TEST_KEY_PATH=/path/to/test.key \\
    ARCA_TEST_CUIT=20123456789 \\
    pytest tests/e2e/test_lookup_e2e.py -v -m e2e

Para excluirlos del run normal:
    pytest -m "not e2e"
"""

import os
from pathlib import Path

import pytest

from arca_mcp.errors import ArcaError
from arca_mcp.padron import client as padron_client
from arca_mcp.wsaa import WsaaEnvironment, validate_wsaa_login
from arca_mcp.wsfe import client as wsfe_client

CERT_PATH = os.environ.get("ARCA_TEST_CERT_PATH")
KEY_PATH = os.environ.get("ARCA_TEST_KEY_PATH")
TEST_CUIT = os.environ.get("ARCA_TEST_CUIT")

_has_credentials = bool(CERT_PATH and KEY_PATH)
_has_cuit = bool(TEST_CUIT)

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not _has_credentials,
        reason="No hay certificado configurado para E2E (ARCA_TEST_CERT_PATH / ARCA_TEST_KEY_PATH no seteados)",
    ),
]


@pytest.fixture(scope="module")
def wsfe_auth() -> tuple[str, str]:
    """Obtiene token y sign de WSAA para WSFEv1 (homologación).

    Skipea si las credenciales no están disponibles.
    """
    if not _has_credentials:
        pytest.skip("No hay certificado configurado para E2E")

    cert = Path(CERT_PATH)
    key = Path(KEY_PATH)

    if not cert.exists():
        pytest.fail(f"ARCA_TEST_CERT_PATH no existe: {cert}")
    if not key.exists():
        pytest.fail(f"ARCA_TEST_KEY_PATH no existe: {key}")

    result = validate_wsaa_login(
        cert, key, service="wsfe", environment=WsaaEnvironment.HOMOLOGACION
    )
    if not result.ok or result.token is None:
        pytest.skip(f"WSAA login para wsfe falló: {result.message}")

    return result.token.token, result.token.sign


@pytest.fixture(scope="module")
def padron_auth() -> tuple[str, str]:
    """Obtiene token y sign de WSAA para ws_sr_padron_a4 (homologación).

    Skipea explícitamente si el certificado no tiene autorización para el padrón.
    """
    if not _has_credentials:
        pytest.skip("No hay certificado configurado para E2E")

    cert = Path(CERT_PATH)
    key = Path(KEY_PATH)

    if not cert.exists():
        pytest.fail(f"ARCA_TEST_CERT_PATH no existe: {cert}")
    if not key.exists():
        pytest.fail(f"ARCA_TEST_KEY_PATH no existe: {key}")

    result = validate_wsaa_login(
        cert, key, service="ws_sr_padron_a4", environment=WsaaEnvironment.HOMOLOGACION
    )
    if not result.ok or result.token is None:
        pytest.skip(
            f"El certificado no tiene acceso a ws_sr_padron_a4 en homologación: {result.message}"
        )

    return result.token.token, result.token.sign


class TestGetVoucherTypesE2E:
    """E2E: get_voucher_types contra WSFEv1 homologación."""

    def test_returns_non_empty_list(self, wsfe_auth):
        """WSFEv1 debe retornar al menos un tipo de comprobante."""
        if not _has_cuit:
            pytest.skip("ARCA_TEST_CUIT no seteado")
        token, sign = wsfe_auth
        result = wsfe_client.get_voucher_types(token, sign, "homologacion", TEST_CUIT)
        assert not isinstance(result, ArcaError), (
            f"get_voucher_types retornó ArcaError: {result}"
        )
        assert len(result) > 0, "La lista de tipos de comprobante está vacía"

    def test_factura_a_present(self, wsfe_auth):
        """Factura A (id='1') debe estar en el catálogo."""
        if not _has_cuit:
            pytest.skip("ARCA_TEST_CUIT no seteado")
        token, sign = wsfe_auth
        result = wsfe_client.get_voucher_types(token, sign, "homologacion", TEST_CUIT)
        assert not isinstance(result, ArcaError), (
            f"get_voucher_types retornó ArcaError: {result}"
        )
        ids = {item.id for item in result}
        assert "1" in ids, f"Factura A (id=1) no encontrada en el catálogo: {ids}"

    def test_factura_b_present(self, wsfe_auth):
        """Factura B (id='6') debe estar en el catálogo."""
        if not _has_cuit:
            pytest.skip("ARCA_TEST_CUIT no seteado")
        token, sign = wsfe_auth
        result = wsfe_client.get_voucher_types(token, sign, "homologacion", TEST_CUIT)
        assert not isinstance(result, ArcaError), (
            f"get_voucher_types retornó ArcaError: {result}"
        )
        ids = {item.id for item in result}
        assert "6" in ids, f"Factura B (id=6) no encontrada en el catálogo: {ids}"

    def test_each_item_has_id_and_description(self, wsfe_auth):
        """Cada tipo de comprobante debe tener id y descripción no vacíos."""
        if not _has_cuit:
            pytest.skip("ARCA_TEST_CUIT no seteado")
        token, sign = wsfe_auth
        result = wsfe_client.get_voucher_types(token, sign, "homologacion", TEST_CUIT)
        assert not isinstance(result, ArcaError), (
            f"get_voucher_types retornó ArcaError: {result}"
        )
        for item in result:
            assert item.id, f"CatalogItem sin id: {item}"
            assert item.description, f"CatalogItem sin description: {item}"


class TestGetTaxpayerDetailsE2E:
    """E2E: get_taxpayer_details contra ws_sr_padron_a4 homologación.

    Requiere además ARCA_TEST_CUIT seteado — skipea con mensaje explícito si no está.
    """

    def test_known_cuit_returns_persona_details(self, padron_auth):
        """Un CUIT conocido debe retornar PersonaDetails con datos válidos."""
        if not TEST_CUIT:
            pytest.skip(
                "ARCA_TEST_CUIT no seteado — no se puede consultar el padrón sin CUIT de prueba"
            )

        token, sign = padron_auth
        result = padron_client.get_persona(
            token=token,
            sign=sign,
            emitter_cuit=TEST_CUIT,
            query_cuit=TEST_CUIT,
            environment="homologacion",
        )
        assert not isinstance(result, ArcaError), (
            f"get_persona retornó ArcaError para CUIT {TEST_CUIT}: {result}"
        )
        assert result.cuit == TEST_CUIT, (
            f"CUIT retornado ({result.cuit}) difiere del consultado ({TEST_CUIT})"
        )
        assert result.status in ("ACTIVO", "INACTIVO"), (
            f"Estado inesperado: {result.status!r}"
        )

    def test_invalid_cuit_returns_arca_error(self, padron_auth):
        """Un CUIT inexistente debe retornar ArcaError (PADRON_NOT_FOUND o SERVICE_ERROR)."""
        if not TEST_CUIT:
            pytest.skip(
                "ARCA_TEST_CUIT no seteado — se necesita para ser usado como emitter_cuit"
            )

        token, sign = padron_auth
        # CUIT de formato válido pero que no existe en padrón
        NONEXISTENT_CUIT = "20000000000"
        result = padron_client.get_persona(
            token=token,
            sign=sign,
            emitter_cuit=TEST_CUIT,
            query_cuit=NONEXISTENT_CUIT,
            environment="homologacion",
        )
        assert isinstance(result, ArcaError), (
            f"Se esperaba ArcaError para CUIT inexistente {NONEXISTENT_CUIT}, "
            f"pero se obtuvo: {result}"
        )
