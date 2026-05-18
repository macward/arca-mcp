import time
from pathlib import Path

import httpx

import arca_mcp.wsaa.token_store as token_store
from arca_mcp.certificates.errors import CertificateLoadError, PrivateKeyLoadError
from arca_mcp.errors import ArcaErrorCause
from arca_mcp.wsaa.client import (
    WsaaEnvironment,
    call_login_cms,
    parse_login_ticket_response,
)
from arca_mcp.wsaa.models import SetupCheckResult, WsaaToken
from arca_mcp.wsaa.signing import sign_tra
from arca_mcp.wsaa.token_cache import TokenCache
from arca_mcp.wsaa.tra import build_tra
from arca_mcp.wsaa.wsaa_logger import WsaaCallResult, log_wsaa_call


def validate_wsaa_login(
    cert_path: Path,
    key_path: Path,
    service: str = "wsfe",
    environment: WsaaEnvironment = WsaaEnvironment.HOMOLOGACION,
    cuit: str | None = None,
) -> SetupCheckResult:
    """Ejecuta el flujo completo de login WSAA y retorna el resultado.

    - Construye un TRA para el servicio indicado
    - Lo firma con CMS usando cert + key
    - Lo envía a WSAA homologación o producción
    - Parsea la respuesta y retorna el token + sign

    Si `cuit` se provee, se consulta el caché filesystem antes del login de red
    y se persiste el token obtenido.

    Si algún paso falla, retorna SetupCheckResult.ok=False con la causa.
    """
    _cuit = cuit or "unknown"
    _start = time.monotonic()

    def _log(result: WsaaCallResult, error_cause: str | None = None) -> None:
        latency_ms = int((time.monotonic() - _start) * 1000)
        log_wsaa_call(_cuit, service, latency_ms, result, error_cause)

    cached = token_store.get_token(str(cert_path), str(key_path), str(environment), str(service))
    if cached is not None:
        token, sign = cached
        _log(WsaaCallResult.CACHED)
        return SetupCheckResult(
            ok=True,
            message=f"Token WSAA cacheado para servicio {service!r}.",
            token=WsaaToken(token=token, sign=sign, generation_time="cached", expiration_time="cached"),
        )

    fs_cache: TokenCache | None = None
    if cuit is not None:
        fs_cache = TokenCache()
        cached_token = fs_cache.get(cuit)
        if cached_token is not None:
            token_store.put_token(
                str(cert_path), str(key_path), str(environment), str(service),
                cached_token.token, cached_token.sign, cached_token.expiration_time,
            )
            _log(WsaaCallResult.CACHED)
            return SetupCheckResult(
                ok=True,
                message=f"Token WSAA restaurado del caché para servicio {service!r}.",
                token=cached_token,
            )

    try:
        tra = build_tra(service)
    except Exception as e:
        _log(WsaaCallResult.FAILED, error_cause=f"tra_build_error: {e}")
        return SetupCheckResult(
            ok=False,
            cause=ArcaErrorCause.WSAA_AUTH_FAILED,
            message=f"Error generando TRA: {e}",
        )

    try:
        cms = sign_tra(tra, cert_path, key_path)
    except CertificateLoadError as e:
        _log(WsaaCallResult.FAILED, error_cause=f"cert_invalid: {e}")
        return SetupCheckResult(ok=False, cause=ArcaErrorCause.CERT_INVALID, message=str(e))
    except PrivateKeyLoadError as e:
        _log(WsaaCallResult.FAILED, error_cause=f"key_invalid: {e}")
        return SetupCheckResult(ok=False, cause=ArcaErrorCause.KEY_INVALID, message=str(e))
    except Exception as e:
        _log(WsaaCallResult.FAILED, error_cause=f"signing_error: {e}")
        return SetupCheckResult(
            ok=False,
            cause=ArcaErrorCause.WSAA_AUTH_FAILED,
            message=f"Error firmando TRA: {e}",
        )

    _was_retried = False

    def _on_retry(_attempt: int) -> None:
        nonlocal _was_retried
        _was_retried = True

    try:
        response_xml = call_login_cms(cms, endpoint=environment.value, on_retry=_on_retry)
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
        # WSAA rate-limita: si ya emitió un TA vivo para este servicio, rechaza
        # nuevos pedidos. Semánticamente es éxito (el auth funciona), pero no
        # tenemos token porque WSAA no lo re-emite.
        if "ya posee un ta valido" in msg_lower or "ya posee un ta válido" in msg_lower:
            _log(WsaaCallResult.CACHED)
            return SetupCheckResult(
                ok=True,
                message=(
                    f"WSAA confirma auth previa válida para {service!r} "
                    "(no se re-emite token mientras el TA anterior siga vivo). "
                    "Proveer el parámetro `cuit` para usar el caché filesystem."
                ),
            )
        cause = ArcaErrorCause.WSAA_AUTH_FAILED
        if "computador no autorizado" in msg_lower or "alias" in msg_lower:
            cause = ArcaErrorCause.SERVICE_UNAUTHORIZED
        _log(WsaaCallResult.FAILED, error_cause=f"soap_fault: {msg}")
        return SetupCheckResult(ok=False, cause=cause, message=msg)

    try:
        token, sign, gen, exp = parse_login_ticket_response(response_xml)
    except Exception as e:
        _log(WsaaCallResult.FAILED, error_cause=f"parse_error: {e}")
        return SetupCheckResult(
            ok=False,
            cause=ArcaErrorCause.WSAA_AUTH_FAILED,
            message=f"Error parseando respuesta WSAA: {e}",
        )

    wsaa_token = WsaaToken(token=token, sign=sign, generation_time=gen, expiration_time=exp)
    token_store.put_token(str(cert_path), str(key_path), str(environment), str(service), token, sign, exp)
    if fs_cache is not None and cuit is not None:
        fs_cache.save(cuit, wsaa_token)

    _log(WsaaCallResult.RETRIED if _was_retried else WsaaCallResult.OK)
    return SetupCheckResult(ok=True, token=wsaa_token)


def validate_service_authorization(
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

    return validate_wsaa_login(cert_path, key_path, service=service, environment=environment)
