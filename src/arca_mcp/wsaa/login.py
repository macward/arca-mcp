import asyncio
import time
from pathlib import Path

import httpx

from arca_mcp.certificates.errors import CertificateLoadError, PrivateKeyLoadError
from arca_mcp.errors import ArcaErrorCause
from arca_mcp.wsaa.client import (
    WsaaEnvironment,
    call_login_cms,
    parse_login_ticket_response,
)
from arca_mcp.wsaa.models import SetupCheckResult, WsaaToken
from arca_mcp.wsaa.signing import sign_tra
from arca_mcp.wsaa.tra import build_tra
from arca_mcp.wsaa.wsaa_cache import WsaaCache
from arca_mcp.wsaa.wsaa_logger import WsaaCallResult, log_wsaa_call

# Eagerly initialized at module load — one instance per process, no per-request I/O.
_shared_cache: WsaaCache = WsaaCache()


async def validate_wsaa_login(
    cert_path: Path,
    key_path: Path,
    service: str = "wsfe",
    environment: WsaaEnvironment = WsaaEnvironment.HOMOLOGACION,
    cuit: str | None = None,
    *,
    cache: WsaaCache | None = None,
) -> SetupCheckResult:
    """Ejecuta el flujo completo de login WSAA y retorna el resultado.

    - Construye un TRA para el servicio indicado
    - Lo firma con CMS usando cert + key
    - Lo envía a WSAA homologación o producción
    - Parsea la respuesta y retorna el token + sign

    Si `cuit` se provee, se consulta el caché (in-memory → filesystem) antes del
    login de red y se persiste el token obtenido. WsaaCache usa threading.Lock
    para la capa in-memory y asyncio.Lock por CUIT para la capa filesystem,
    previniendo doble-login cuando múltiples requests concurrentes tocan el mismo
    CUIT simultáneamente.

    Si algún paso falla, retorna SetupCheckResult.ok=False con la causa.
    """
    _cuit = cuit or "unknown"
    _start = time.monotonic()
    _was_retried = False
    _network_called = False

    def _log(result: WsaaCallResult, error_cause: str | None = None) -> None:
        latency_ms = int((time.monotonic() - _start) * 1000)
        log_wsaa_call(_cuit, service, latency_ms, result, error_cause)

    _active_cache: WsaaCache = cache if cache is not None else _shared_cache

    # Derive a stable cache key even when no CUIT is provided.
    # For CUIT-aware callers the key is (cuit, service).
    # For anonymous callers we fall back to a composite key from cert+key+env.
    _mem_cuit = cuit if cuit is not None else f"{cert_path}:{key_path}:{environment}"

    # In-memory fast path — no I/O
    cached_token = _active_cache.get(_mem_cuit, service)
    if cached_token is not None:
        _log(WsaaCallResult.CACHED)
        return SetupCheckResult(
            ok=True,
            message=f"Token WSAA cacheado para servicio {service!r}.",
            token=cached_token,
        )

    def _do_network_login() -> WsaaToken:
        """TRA build → CMS sign → WSAA HTTP → parse."""
        nonlocal _was_retried, _network_called
        _network_called = True

        tra = build_tra(service)
        cms = sign_tra(tra, cert_path, key_path)

        def _on_retry(_: int) -> None:
            nonlocal _was_retried
            _was_retried = True

        response_xml = call_login_cms(cms, endpoint=environment.value, on_retry=_on_retry)
        token, sign, gen, exp = parse_login_ticket_response(response_xml)
        return WsaaToken(token=token, sign=sign, generation_time=gen, expiration_time=exp)

    try:
        if cuit is not None:
            # Full path: in-memory check-lock-check + filesystem persistence
            wsaa_token = await _active_cache.get_or_refresh(cuit, service, _do_network_login)
        else:
            # Anonymous path: network login + warm in-memory only (no filesystem)
            wsaa_token = await asyncio.to_thread(_do_network_login)
    except CertificateLoadError as e:
        _log(WsaaCallResult.FAILED, error_cause=f"cert_invalid: {e}")
        return SetupCheckResult(ok=False, cause=ArcaErrorCause.CERT_INVALID, message=str(e))
    except PrivateKeyLoadError as e:
        _log(WsaaCallResult.FAILED, error_cause=f"key_invalid: {e}")
        return SetupCheckResult(ok=False, cause=ArcaErrorCause.KEY_INVALID, message=str(e))
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        _log(WsaaCallResult.FAILED, error_cause=f"wsaa_unreachable: {e}")
        return SetupCheckResult(
            ok=False,
            cause=ArcaErrorCause.WSAA_UNREACHABLE,
            message=f"No se pudo conectar a WSAA: {e}",
        )
    except httpx.HTTPStatusError as e:
        _log(WsaaCallResult.FAILED, error_cause=f"http_{e.response.status_code}")
        return SetupCheckResult(
            ok=False,
            cause=ArcaErrorCause.WSAA_AUTH_FAILED,
            message=f"WSAA respondió HTTP {e.response.status_code}",
        )
    except ValueError as e:
        msg = str(e)
        msg_lower = msg.lower()
        if "ya posee un ta valido" in msg_lower or "ya posee un ta válido" in msg_lower:
            _log(WsaaCallResult.CACHED)
            return SetupCheckResult(
                ok=False,
                cause=ArcaErrorCause.WSAA_TA_ALREADY_VALID,
                message=(
                    f"WSAA ya tiene un TA válido para {service!r}. "
                    "Proveer el parámetro `cuit` para recuperar el token desde el caché filesystem."
                ),
            )
        cause = ArcaErrorCause.WSAA_AUTH_FAILED
        if "computador no autorizado" in msg_lower or "alias" in msg_lower:
            cause = ArcaErrorCause.SERVICE_UNAUTHORIZED
        _log(WsaaCallResult.FAILED, error_cause=f"soap_fault: {msg}")
        return SetupCheckResult(ok=False, cause=cause, message=msg)
    except Exception as e:
        _log(WsaaCallResult.FAILED, error_cause=f"error: {e}")
        return SetupCheckResult(
            ok=False,
            cause=ArcaErrorCause.WSAA_AUTH_FAILED,
            message=str(e),
        )

    if not wsaa_token.token or not wsaa_token.sign:
        _log(WsaaCallResult.FAILED, error_cause="empty_token_or_sign")
        return SetupCheckResult(
            ok=False,
            cause=ArcaErrorCause.WSAA_AUTH_FAILED,
            message="WSAA retornó un token o firma vacíos.",
        )

    # Warm in-memory cache for anonymous callers (cuit-aware path already warmed it via get_or_refresh)
    if _network_called:
        _active_cache.set(_mem_cuit, service, wsaa_token)

    if not _network_called:
        _log(WsaaCallResult.CACHED)
        return SetupCheckResult(
            ok=True,
            message=f"Token WSAA restaurado del caché para servicio {service!r}.",
            token=wsaa_token,
        )
    _log(WsaaCallResult.RETRIED if _was_retried else WsaaCallResult.OK)
    return SetupCheckResult(ok=True, token=wsaa_token)


async def validate_service_authorization(
    cert_path: Path,
    key_path: Path,
    service: str,
    environment: WsaaEnvironment = WsaaEnvironment.HOMOLOGACION,
) -> SetupCheckResult:
    """Verifica que el certificado tenga acceso autorizado a un servicio ARCA.

    Acepta cualquier string como servicio. Si querés autocompletar contra los
    servicios más comunes, usá el enum `ArcaService`.

    Si WSAA responde con éxito → el cert tiene acceso autorizado.
    Si WSAA rechaza con "computador no autorizado" o "alias no registrado"
    → SERVICE_UNAUTHORIZED.
    """
    if not service or not service.strip():
        return SetupCheckResult(
            ok=False,
            cause=ArcaErrorCause.SERVICE_UNAUTHORIZED,
            message="El servicio no puede estar vacío",
        )

    return await validate_wsaa_login(cert_path, key_path, service=service, environment=environment)
