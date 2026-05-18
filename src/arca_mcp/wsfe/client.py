"""Cliente SOAP para WSFEv1 — consultas paramétricas.

Solo implementa las operaciones de catálogo (FEParamGet*) que no requieren
emitir comprobantes. No incluye operaciones de escritura.

Convención de retorno:
    Todas las funciones retornan `list[CatalogItem] | ArcaError`.
    Nunca lanzan excepciones crudas — toda falla cruza la frontera MCP como
    un ArcaError estructurado (igual que `resolve_runtime_config`).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Union

import zeep
import zeep.exceptions

from arca_mcp.errors import ArcaError, ArcaErrorCause
from arca_mcp.wsfe.models import CatalogItem


class WsfeEnvironment(StrEnum):
    HOMOLOGACION = "https://wswhomo.afip.gov.ar/wsfev1/service.asmx?WSDL"
    PRODUCCION = "https://servicios1.afip.gov.ar/wsfev1/service.asmx?WSDL"


def _build_auth(token: str, sign: str) -> dict:
    """Construye el dict Auth para las operaciones paramétricas de WSFEv1.

    Las consultas paramétricas (FEParamGet*) no requieren Cuit real.
    Se pasa Cuit=0 para satisfacer el schema del servicio.
    """
    return {"Token": token, "Sign": sign, "Cuit": 0}


def _wsdl_url(environment: str) -> str:
    """Retorna la URL del WSDL según el ambiente."""
    if environment == "produccion":
        return WsfeEnvironment.PRODUCCION
    return WsfeEnvironment.HOMOLOGACION


def _parse_catalog(items) -> list[CatalogItem]:
    """Convierte los items de zeep a lista de CatalogItem."""
    result = []
    for item in items:
        item_id = str(getattr(item, "Id", "") or "")
        desc = str(getattr(item, "Desc", "") or "")
        result.append(CatalogItem(id=item_id, description=desc))
    return result


def _call_wsfe(
    wsdl_url: str,
    method: str,
    auth: dict,
) -> Union[list[CatalogItem], ArcaError]:
    """Llama a un método FEParamGet* de WSFEv1 y retorna lista de CatalogItem.

    Retorna ArcaError si zeep falla por red, SOAP Fault, o error en la
    respuesta AFIP. Nunca lanza excepciones crudas.
    """
    try:
        client = zeep.Client(wsdl=wsdl_url)
        response = getattr(client.service, method)(Auth=auth)
    except zeep.exceptions.Fault as exc:
        return ArcaError(
            cause=ArcaErrorCause.ARCA_SERVICE_ERROR,
            message=f"WSFEv1 SOAP Fault en {method}: {exc.message}",
        )
    except Exception as exc:
        return ArcaError(
            cause=ArcaErrorCause.ARCA_SERVICE_ERROR,
            message=f"Error de comunicación con WSFEv1 ({method}): {exc}",
        )

    # Verificar errores en el cuerpo de la respuesta AFIP
    errors = getattr(response, "Errors", None)
    if errors is not None:
        error_list = getattr(errors, "Err", None) or []
        if error_list:
            msgs = "; ".join(
                f"[{getattr(e, 'Code', '?')}] {getattr(e, 'Msg', '')}"
                for e in error_list
            )
            return ArcaError(
                cause=ArcaErrorCause.ARCA_SERVICE_ERROR,
                message=f"WSFEv1 error en {method}: {msgs}",
            )

    # Extraer la lista de resultados — el wrapper varía por método pero
    # ResultGet siempre contiene un objeto iterable de items
    result_data = getattr(response, "ResultGet", None)
    if result_data is None:
        return []

    # ResultGet contiene un atributo con la lista; intentar iterar directamente
    try:
        items = list(result_data)
    except TypeError:
        items = []

    return _parse_catalog(items)


def get_voucher_types(
    token: str, sign: str, environment: str
) -> Union[list[CatalogItem], ArcaError]:
    """Retorna los tipos de comprobante disponibles en WSFEv1."""
    return _call_wsfe(_wsdl_url(environment), "FEParamGetTiposCbte", _build_auth(token, sign))


def get_document_types(
    token: str, sign: str, environment: str
) -> Union[list[CatalogItem], ArcaError]:
    """Retorna los tipos de documento soportados por WSFEv1."""
    return _call_wsfe(_wsdl_url(environment), "FEParamGetTiposDoc", _build_auth(token, sign))


def get_tax_types(
    token: str, sign: str, environment: str
) -> Union[list[CatalogItem], ArcaError]:
    """Retorna los tipos de tributo disponibles en WSFEv1."""
    return _call_wsfe(_wsdl_url(environment), "FEParamGetTiposTributos", _build_auth(token, sign))


def get_aliquot_types(
    token: str, sign: str, environment: str
) -> Union[list[CatalogItem], ArcaError]:
    """Retorna las alícuotas de IVA disponibles en WSFEv1."""
    return _call_wsfe(_wsdl_url(environment), "FEParamGetTiposIva", _build_auth(token, sign))


def get_currency_types(
    token: str, sign: str, environment: str
) -> Union[list[CatalogItem], ArcaError]:
    """Retorna las monedas disponibles en WSFEv1."""
    return _call_wsfe(_wsdl_url(environment), "FEParamGetTiposMonedas", _build_auth(token, sign))
