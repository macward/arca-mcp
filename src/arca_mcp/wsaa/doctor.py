from pathlib import Path

from pydantic import BaseModel

from arca_mcp.certificates import (
    validate_cert_key_match,
    validate_certificate,
    validate_private_key,
)
from arca_mcp.errors import ArcaErrorCause
from arca_mcp.wsaa.client import WsaaEnvironment
from arca_mcp.wsaa.login import validate_service_authorization, validate_wsaa_login


class NamedCheck(BaseModel):
    name: str
    ok: bool
    cause: ArcaErrorCause | None = None
    message: str | None = None
    skipped: bool = False


class SetupDoctorReport(BaseModel):
    checks: list[NamedCheck]
    all_ok: bool
    failed_check: str | None = None


def _skipped(name: str, reason: str) -> NamedCheck:
    return NamedCheck(name=name, ok=False, skipped=True, message=reason)


def run_setup_doctor(
    cert_path: Path,
    key_path: Path,
    service: str = "wsfe",
    environment: WsaaEnvironment = WsaaEnvironment.HOMOLOGACION,
) -> SetupDoctorReport:
    """Ejecuta todas las validaciones del setup técnico en secuencia.

    Short-circuita gracefully: si una validación falla, las downstream se marcan
    como `skipped` para que el agente sepa exactamente dónde está el problema.
    """
    checks: list[NamedCheck] = []
    failed: str | None = None

    # 1. private key
    r = validate_private_key(key_path)
    checks.append(NamedCheck(name="private_key", ok=r.valid, cause=r.cause, message=r.message))
    if not r.valid:
        failed = "private_key"
        checks.append(_skipped("certificate", "saltado por private_key inválida"))
        checks.append(_skipped("cert_key_match", "saltado por private_key inválida"))
        checks.append(_skipped("wsaa_login", "saltado por private_key inválida"))
        checks.append(_skipped("service_authorization", "saltado por private_key inválida"))
        return SetupDoctorReport(checks=checks, all_ok=False, failed_check=failed)

    # 2. certificate
    r = validate_certificate(cert_path)
    checks.append(NamedCheck(name="certificate", ok=r.valid, cause=r.cause, message=r.message))
    if not r.valid:
        failed = "certificate"
        checks.append(_skipped("cert_key_match", "saltado por certificado inválido"))
        checks.append(_skipped("wsaa_login", "saltado por certificado inválido"))
        checks.append(_skipped("service_authorization", "saltado por certificado inválido"))
        return SetupDoctorReport(checks=checks, all_ok=False, failed_check=failed)

    # 3. cert + key match
    r = validate_cert_key_match(cert_path, key_path)
    checks.append(NamedCheck(name="cert_key_match", ok=r.valid, cause=r.cause, message=r.message))
    if not r.valid:
        failed = "cert_key_match"
        checks.append(_skipped("wsaa_login", "saltado por cert/key mismatch"))
        checks.append(_skipped("service_authorization", "saltado por cert/key mismatch"))
        return SetupDoctorReport(checks=checks, all_ok=False, failed_check=failed)

    # 4. WSAA login
    s = validate_wsaa_login(cert_path, key_path, service=service, environment=environment)
    checks.append(NamedCheck(name="wsaa_login", ok=s.ok, cause=s.cause, message=s.message))
    if not s.ok:
        failed = "wsaa_login"
        checks.append(_skipped("service_authorization", "saltado por fallo en wsaa_login"))
        return SetupDoctorReport(checks=checks, all_ok=False, failed_check=failed)

    # 5. service authorization (mismo flujo que wsaa_login, ya se sabe que funciona)
    s = validate_service_authorization(cert_path, key_path, service=service, environment=environment)
    checks.append(NamedCheck(name="service_authorization", ok=s.ok, cause=s.cause, message=s.message))
    if not s.ok:
        failed = "service_authorization"
        return SetupDoctorReport(checks=checks, all_ok=False, failed_check=failed)

    return SetupDoctorReport(checks=checks, all_ok=True)
