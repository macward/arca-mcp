from enum import StrEnum

import httpx
from lxml import etree


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


_TRANSIENT_ERRORS = (httpx.ConnectError, httpx.TimeoutException)


def call_login_cms(
    cms_b64: str,
    endpoint: str,
    timeout: float = 30.0,
    retries: int = 1,
) -> str:
    """Llama al método loginCms de WSAA y retorna el XML del loginTicketResponse.

    `retries` es el número de reintentos adicionales ante fallos transitorios
    de red (`ConnectError`, `TimeoutException`). Total de intentos = retries + 1.

    Lanza httpx.HTTPError si la conexión falla tras los reintentos.
    Lanza ValueError si WSAA devuelve un SOAP Fault.
    """
    body = SOAP_ENVELOPE_TEMPLATE.format(cms=cms_b64).encode("utf-8")
    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": "",
    }

    attempts = max(retries, 0) + 1
    last_exc: Exception | None = None
    with httpx.Client(verify=True, timeout=timeout) as client:
        for _ in range(attempts):
            try:
                response = client.post(endpoint, content=body, headers=headers)
                break
            except _TRANSIENT_ERRORS as exc:
                last_exc = exc
        else:
            assert last_exc is not None
            raise last_exc
    response.raise_for_status()

    root = etree.fromstring(response.content)

    ns = {"soapenv": "http://schemas.xmlsoap.org/soap/envelope/"}
    fault = root.find(".//soapenv:Fault", ns)
    if fault is not None:
        fault_string = fault.findtext("faultstring") or "Fault sin detalle"
        raise ValueError(f"WSAA SOAP Fault: {fault_string}")

    login_response = root.find(".//{*}loginCmsReturn")
    if login_response is None or login_response.text is None:
        raise ValueError("Respuesta WSAA sin loginCmsReturn")

    return login_response.text


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
