from collections.abc import Callable
from enum import StrEnum

import httpx
from lxml import etree

from arca_mcp.wsaa.retry import with_retry


class WsaaEnvironment(StrEnum):
    HOMOLOGACION = "https://wsaahomo.afip.gov.ar/ws/services/LoginCms"
    PRODUCCION = "https://wsaa.afip.gov.ar/ws/services/LoginCms"


SOAP_ENVELOPE_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:wsaa="http://wsaa.view.sua.dvadac.desein.afip.gov">
  <soapenv:Header/>
  <soapenv:Body>
    <wsaa:loginCms>
      <wsaa:in0>{cms}</wsaa:in0>
    </wsaa:loginCms>
  </soapenv:Body>
</soapenv:Envelope>"""


def call_login_cms(
    cms_b64: str,
    endpoint: str,
    timeout: float = 30.0,
    max_attempts: int = 2,
    on_retry: Callable[[int], None] | None = None,
) -> str:
    """Llama al método loginCms de WSAA y retorna el XML del loginTicketResponse.

    Reintenta ante fallos transitorios de red con backoff exponencial (100ms → 500ms).
    `max_attempts=2` significa 1 intento inicial + 1 reintento.
    `on_retry(attempt)` se llama antes de cada reintento (1-based).

    Lanza httpx.HTTPError si la conexión falla tras los reintentos.
    Lanza ValueError si WSAA devuelve un SOAP Fault.
    """
    body = SOAP_ENVELOPE_TEMPLATE.format(cms=cms_b64).encode("utf-8")
    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": "",
    }

    with httpx.Client(verify=True, timeout=timeout) as client:
        response = with_retry(
            lambda: client.post(endpoint, content=body, headers=headers),
            max_attempts=max_attempts,
            on_retry=on_retry,
        )

    # WSAA devuelve SOAP Faults dentro de HTTP 500 con el detalle real
    # (ej. "Computador no autorizado a acceder al servicio"). Hay que parsear
    # el body antes de raise_for_status() para no perder el mensaje legible.
    fault_string = _extract_soap_fault(response.content)
    if fault_string is not None:
        raise ValueError(f"WSAA SOAP Fault: {fault_string}")

    response.raise_for_status()

    root = etree.fromstring(response.content)
    login_response = root.find(".//{*}loginCmsReturn")
    if login_response is None or login_response.text is None:
        raise ValueError("Respuesta WSAA sin loginCmsReturn")

    return login_response.text


def _extract_soap_fault(content: bytes) -> str | None:
    """Devuelve el faultstring si el body es un SOAP Fault, None en caso contrario."""
    try:
        root = etree.fromstring(content)
    except etree.XMLSyntaxError:
        return None
    fault = root.find(".//{http://schemas.xmlsoap.org/soap/envelope/}Fault")
    if fault is None:
        return None
    return fault.findtext("faultstring") or "Fault sin detalle"


def parse_login_ticket_response(xml: str) -> tuple[str, str, str, str]:
    """Parsea el loginTicketResponse y retorna (token, sign, generation_time, expiration_time)."""
    root = etree.fromstring(xml.encode("utf-8") if isinstance(xml, str) else xml)

    credentials = root.find("credentials")
    if credentials is None:
        raise ValueError("loginTicketResponse sin credentials")

    token = credentials.findtext("token")
    sign = credentials.findtext("sign")
    header = root.find("header")
    generation = header.findtext("generationTime") if header is not None else None
    expiration = header.findtext("expirationTime") if header is not None else None

    if not token or not sign or not generation or not expiration:
        raise ValueError("loginTicketResponse incompleto")

    return token, sign, generation, expiration
