"""E2E tests contra wsaahomo.afip.gov.ar (homologación real).

Requieren env vars:
- ARCA_TEST_CERT_PATH: path al .crt de homologación
- ARCA_TEST_KEY_PATH: path al .key (RSA, sin password)
- ARCA_TEST_SERVICE: opcional, default "wsfe"

Si las env vars no están seteadas, todos los tests skipean automáticamente.

Para correrlos:
    ARCA_TEST_CERT_PATH=/path/to/test.crt \\
    ARCA_TEST_KEY_PATH=/path/to/test.key \\
    pytest tests/test_e2e_wsaa.py -v -m e2e

Para excluirlos del run normal:
    pytest -m "not e2e"
"""

import os
from pathlib import Path

import pytest

from arca_mcp.wsaa import WsaaEnvironment, run_setup_doctor


CERT_PATH = os.environ.get("ARCA_TEST_CERT_PATH")
KEY_PATH = os.environ.get("ARCA_TEST_KEY_PATH")
SERVICE = os.environ.get("ARCA_TEST_SERVICE", "wsfe")


pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not (CERT_PATH and KEY_PATH),
        reason="ARCA_TEST_CERT_PATH y ARCA_TEST_KEY_PATH no seteados — skip E2E",
    ),
]


@pytest.fixture(scope="module")
def cert_paths() -> tuple[Path, Path]:
    cert = Path(CERT_PATH)
    key = Path(KEY_PATH)
    if not cert.exists():
        pytest.fail(f"ARCA_TEST_CERT_PATH no existe: {cert}")
    if not key.exists():
        pytest.fail(f"ARCA_TEST_KEY_PATH no existe: {key}")
    return cert, key


async def test_e2e_setup_doctor_all_green(cert_paths):
    """E2E: el orquestador completo pasa los 5 checks contra homologación real.

    Nota: AFIP rate-limita las TA requests (mientras un TA está vivo, WSAA
    rechaza pedir otro para el mismo servicio con "El CEE ya posee un TA
    valido"). Por eso este test único cubre todo el pipeline en una sola
    llamada a WSAA — no se puede romper en sub-tests sin caché de token.
    """
    cert, key = cert_paths
    report = await run_setup_doctor(
        cert, key, service=SERVICE, environment=WsaaEnvironment.HOMOLOGACION
    )

    failed = [c for c in report.checks if not c.ok and not c.skipped]
    skipped = [c for c in report.checks if c.skipped]

    assert report.all_ok, (
        f"Setup doctor falló. failed_check={report.failed_check}\n"
        f"  fallidos: {[(c.name, c.cause, c.message) for c in failed]}\n"
        f"  skipped: {[c.name for c in skipped]}"
    )
    assert len(report.checks) == 5
    assert all(c.ok for c in report.checks)
