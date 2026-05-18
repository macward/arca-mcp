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
from arca_mcp.wsaa.tra import build_tra


def validate_wsaa_login(
    cert_path: Path,
    key_path: Path,
    service: str = "wsfe",
    environment: WsaaEnvironment = WsaaEnvironment.HOMOLOGACION,
) -> SetupCheckResult:
    """Ejecuta el flujo completo de login WSAA y retorna el resultado.

    - Construye un TRA para el servicio indicado
    - Lo firma con CMS usando cert + key
    - Lo envía a WSAA homologación o producción
    - Parsea la respuesta y retorna el token + sign

    Si algún paso falla, retorna SetupCheckResult.ok=False con la causa.
    """
    cached = token_store.get_token(str(cert_path), str(key_path), str(environment), str(service))
    if cached is not None:
        token, sign = cached
        return SetupCheckResult(
            ok=True,
            message=f"Token WSAA cacheado para servicio {service!r}.",
            token=WsaaToken(token=token, sign=sign, generation_time="cached", expiration_time="cached"),
        )

    try:
        tra = build_tra(service)
    except Exception as e:
        return SetupCheckResult(
            ok=False,
            cause=ArcaErrorCause.WSAA_AUTH_FAILED,
            message=f"Error generando TRA: {e}",
        )

    try:
        cms = sign_tra(tra, cert_path, key_path)
    except CertificateLoadError as e:
        return SetupCheckResult(ok=False, cause=ArcaErrorCause.CERT_INVALID, message=str(e))
    except PrivateKeyLoadError as e:
        return SetupCheckResult(ok=False, cause=ArcaErrorCause.KEY_INVALID, message=str(e))
    except Exception as e:
        return SetupCheckResult(
            ok=False,
            cause=ArcaErrorCause.WSAA_AUTH_FAILED,
            message=f"Error firmando TRA: {e}",
        )

    try:
        response_xml = call_login_cms(cms, endpoint=environment.value)
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        return SetupCheckResult(
            ok=False,
            cause=ArcaErrorCause.WSAA_UNREACHABLE,
            message=f"No se pudo conectar a WSAA: {e}",
        )
    except httpx.HTTPStatusError as e:
        return SetupCheckResult(
            ok=False,
            cause=ArcaErrorCause.WSAA_AUTH_FAILED,
            message=f"WSAA respondió HTTP {e.response.status_code}",
        )
    except ValueError as e:
        # SOAP Fault o respuesta inválida
        msg = str(e)
        msg_lower = msg.lower()
        # WSAA rate-limita: si ya emitió un TA vivo para este servicio, rechaza
        # nuevos pedidos. Semánticamente es éxito (el auth funciona), pero no
        # tenemos token porque WSAA no lo re-emite. Resolverlo bien requiere
        # caché de token (v0.3); por ahora lo reportamos como ok con mensaje.
        if "ya posee un ta valido" in msg_lower or "ya posee un ta válido" in msg_lower:
            return SetupCheckResult(
                ok=True,
                message=(
                    f"WSAA confirma auth previa válida para {service!r} "
                    "(no se re-emite token mientras el TA anterior siga vivo). "
                    "Caché de token llegará en v0.3."
                ),
            )
        cause = ArcaErrorCause.WSAA_AUTH_FAILED
        if "computador no autorizado" in msg_lower or "alias" in msg_lower:
            cause = ArcaErrorCause.SERVICE_UNAUTHORIZED
        return SetupCheckResult(ok=False, cause=cause, message=msg)

    try:
        token, sign, gen, exp = parse_login_ticket_response(response_xml)
    except Exception as e:
        return SetupCheckResult(
            ok=False,
            cause=ArcaErrorCause.WSAA_AUTH_FAILED,
            message=f"Error parseando respuesta WSAA: {e}",
        )

    token_store.put_token(str(cert_path), str(key_path), str(environment), str(service), token, sign, exp)

    return SetupCheckResult(
        ok=True,
        token=WsaaToken(token=token, sign=sign, generation_time=gen, expiration_time=exp),
    )


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
