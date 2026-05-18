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


def _build_auth(token: str, sign: str, cuit: str | int) -> dict | ArcaError:
    """Construye el dict Auth para las operaciones paramétricas de WSFEv1.

    WSFE requiere Cuit real aun para consultas paramétricas FEParamGet*.
    """
    try:
        cuit_int = int(cuit)
    except (TypeError, ValueError):
        return ArcaError(
            cause=ArcaErrorCause.MISSING_CONFIG,
            message=f"CUIT emisor inválido para WSFEv1: {cuit!r}",
        )
    return {"Token": token, "Sign": sign, "Cuit": cuit_int}


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


def _extract_result_items(result_data) -> list:
    """Extrae items desde listas directas o wrappers zeep de ResultGet."""
    if result_data is None:
        return []

    if isinstance(result_data, (list, tuple)):
        return list(result_data)

    for attr in (
        "CbteTipo",
        "DocTipo",
        "TributoTipo",
        "IvaTipo",
        "Moneda",
        "OpcionalTipo",
        "ConceptoTipo",
        "PtoVenta",
    ):
        value = getattr(result_data, attr, None)
        if value is not None:
            return list(value) if isinstance(value, (list, tuple)) else [value]

    try:
        return list(result_data)
    except TypeError:
        return []


def _call_wsfe(
    wsdl_url: str,
    method: str,
    auth: dict | ArcaError,
) -> Union[list[CatalogItem], ArcaError]:
    """Llama a un método FEParamGet* de WSFEv1 y retorna lista de CatalogItem.

    Retorna ArcaError si zeep falla por red, SOAP Fault, o error en la
    respuesta AFIP. Nunca lanza excepciones crudas.
    """
    if isinstance(auth, ArcaError):
        return auth

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

    return _parse_catalog(_extract_result_items(result_data))


def get_voucher_types(
    token: str, sign: str, environment: str, cuit: str | int
) -> Union[list[CatalogItem], ArcaError]:
    """Retorna los tipos de comprobante disponibles en WSFEv1."""
    return _call_wsfe(_wsdl_url(environment), "FEParamGetTiposCbte", _build_auth(token, sign, cuit))


def get_document_types(
    token: str, sign: str, environment: str, cuit: str | int
) -> Union[list[CatalogItem], ArcaError]:
    """Retorna los tipos de documento soportados por WSFEv1."""
    return _call_wsfe(_wsdl_url(environment), "FEParamGetTiposDoc", _build_auth(token, sign, cuit))


def get_tax_types(
    token: str, sign: str, environment: str, cuit: str | int
) -> Union[list[CatalogItem], ArcaError]:
    """Retorna los tipos de tributo disponibles en WSFEv1."""
    return _call_wsfe(_wsdl_url(environment), "FEParamGetTiposTributos", _build_auth(token, sign, cuit))


def get_aliquot_types(
    token: str, sign: str, environment: str, cuit: str | int
) -> Union[list[CatalogItem], ArcaError]:
    """Retorna las alícuotas de IVA disponibles en WSFEv1."""
    return _call_wsfe(_wsdl_url(environment), "FEParamGetTiposIva", _build_auth(token, sign, cuit))


def get_currency_types(
    token: str, sign: str, environment: str, cuit: str | int
) -> Union[list[CatalogItem], ArcaError]:
    """Retorna las monedas disponibles en WSFEv1."""
    return _call_wsfe(_wsdl_url(environment), "FEParamGetTiposMonedas", _build_auth(token, sign, cuit))
