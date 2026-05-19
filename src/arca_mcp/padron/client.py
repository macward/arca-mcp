"""Cliente SOAP para ws_sr_padron_a4 — consulta de contribuyentes por CUIT.

Convención de retorno:
    Todas las funciones retornan `PersonaDetails | ArcaError`.
    Nunca lanzan excepciones crudas — toda falla cruza la frontera MCP como
    un ArcaError estructurado (igual que el cliente wsfe).
"""

from __future__ import annotations

import threading
from enum import StrEnum
from typing import Union

import zeep
import zeep.exceptions

from arca_mcp.errors import ArcaError, ArcaErrorCause
from arca_mcp.padron.models import FiscalAddress, PersonaDetails

# One zeep.Client per WSDL URL — avoids re-downloading/parsing the WSDL on every call.
# Lock guards creation under streamable-http where multiple requests run concurrently.
_padron_clients: dict[str, zeep.Client] = {}
_padron_clients_lock = threading.Lock()


def _get_padron_client(wsdl_url: str) -> zeep.Client:
    if wsdl_url in _padron_clients:
        return _padron_clients[wsdl_url]
    with _padron_clients_lock:
        if wsdl_url not in _padron_clients:
            _padron_clients[wsdl_url] = zeep.Client(wsdl=wsdl_url)
    return _padron_clients[wsdl_url]


class PadronEnvironment(StrEnum):
    HOMOLOGACION = "https://awshomo.afip.gov.ar/sr-padron/webservices/personaServiceA4?WSDL"
    PRODUCCION = "https://aws.afip.gov.ar/sr-padron/webservices/personaServiceA4?WSDL"


def _wsdl_url(environment: str) -> str:
    """Retorna la URL del WSDL según el ambiente."""
    if environment == "produccion":
        return PadronEnvironment.PRODUCCION
    return PadronEnvironment.HOMOLOGACION


def _parse_fiscal_address(domicilio) -> FiscalAddress | None:
    """Mapea el domicilioFiscal de la respuesta zeep a FiscalAddress."""
    if domicilio is None:
        return None
    return FiscalAddress(
        street=str(getattr(domicilio, "direccion", "") or "").strip() or None,
        number=str(getattr(domicilio, "numero", "") or "").strip() or None,
        city=str(getattr(domicilio, "localidad", "") or "").strip() or None,
        province=str(getattr(domicilio, "descripcionProvincia", "") or "").strip() or None,
        zip_code=str(getattr(domicilio, "codPostal", "") or "").strip() or None,
    )


def _parse_activities(actividades) -> list[str]:
    """Extrae los códigos de actividad AFIP de la respuesta zeep."""
    if actividades is None:
        return []
    act_list = getattr(actividades, "actividad", None) or []
    result = []
    for act in act_list:
        codigo = getattr(act, "idActividad", None)
        if codigo is not None:
            result.append(str(codigo))
    return result


def _parse_denomination(persona) -> str:
    """Retorna razonSocial para personas jurídicas o apellido + nombre para físicas."""
    razon_social = getattr(persona, "razonSocial", None)
    if razon_social:
        return str(razon_social).strip()
    apellido = str(getattr(persona, "apellido", "") or "").strip()
    nombre = str(getattr(persona, "nombre", "") or "").strip()
    return f"{apellido}, {nombre}".strip(", ") if apellido or nombre else ""


def get_persona(
    token: str,
    sign: str,
    emitter_cuit: str,
    query_cuit: str,
    environment: str,
) -> Union[PersonaDetails, ArcaError]:
    """Consulta el padrón A4 de ARCA para un CUIT dado.

    Args:
        token: Token WSAA obtenido del servicio de autenticación.
        sign: Firma WSAA obtenida del servicio de autenticación.
        emitter_cuit: CUIT del contribuyente que realiza la consulta (cuitRepresentada).
        query_cuit: CUIT a consultar en el padrón (idPersona).
        environment: "homologacion" o "produccion".

    Returns:
        PersonaDetails con los datos del contribuyente, o ArcaError estructurado.
    """
    wsdl_url = _wsdl_url(environment)

    try:
        client = _get_padron_client(wsdl_url)
        response = client.service.getPersona(
            token=token,
            sign=sign,
            cuitRepresentada=emitter_cuit,
            idPersona=query_cuit,
        )
    except zeep.exceptions.Fault as exc:
        return ArcaError(
            cause=ArcaErrorCause.ARCA_SERVICE_ERROR,
            message=f"Padrón A4 SOAP Fault: {exc.message}",
        )
    except Exception as exc:
        return ArcaError(
            cause=ArcaErrorCause.ARCA_SERVICE_ERROR,
            message=f"Error de comunicación con Padrón A4: {exc}",
        )

    # La respuesta puede contener errorConstancia cuando el CUIT no existe
    error_constancia = getattr(response, "errorConstancia", None)
    if error_constancia is not None:
        descripcion = str(getattr(error_constancia, "descripcion", "") or "").strip()
        # Códigos típicos de "no encontrado": 601, 602, etc.
        cod = str(getattr(error_constancia, "codigo", "") or "").strip()
        if cod in ("601", "602") or "no existe" in descripcion.lower() or "no encontrado" in descripcion.lower():
            return ArcaError(
                cause=ArcaErrorCause.PADRON_NOT_FOUND,
                message=f"CUIT {query_cuit} no encontrado en el padrón: {descripcion}",
            )
        return ArcaError(
            cause=ArcaErrorCause.ARCA_SERVICE_ERROR,
            message=f"Error del padrón A4 [{cod}]: {descripcion}",
        )

    persona = getattr(response, "persona", None)
    if persona is None:
        return ArcaError(
            cause=ArcaErrorCause.PADRON_NOT_FOUND,
            message=f"CUIT {query_cuit} no encontrado en el padrón (respuesta vacía)",
        )

    cuit = str(getattr(persona, "idPersona", query_cuit) or query_cuit)
    denomination = _parse_denomination(persona)
    estado_clave = str(getattr(persona, "estadoClave", "") or "").strip()
    domicilio = getattr(persona, "domicilioFiscal", None)
    actividades = getattr(persona, "actividades", None)

    return PersonaDetails(
        cuit=cuit,
        denomination=denomination,
        status=estado_clave,
        fiscal_address=_parse_fiscal_address(domicilio),
        activities=_parse_activities(actividades),
    )
