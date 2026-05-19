"""Cliente SOAP para WSFEv1 — consultas paramétricas y emisión de comprobantes.

Implementa operaciones de catálogo (FEParamGet*) y operaciones de escritura
(FECAESolicitar) y consulta (FECompUltimoAutorizado, FECompConsultar).

Convención de retorno:
    Todas las funciones retornan el tipo de respuesta o `ArcaError`.
    Nunca lanzan excepciones crudas — toda falla cruza la frontera MCP como
    un ArcaError estructurado (igual que `resolve_runtime_config`).
"""

from __future__ import annotations

import threading
from decimal import Decimal
from enum import StrEnum
from typing import Union

import zeep
import zeep.exceptions

from arca_mcp.errors import ArcaError, ArcaErrorCause
from arca_mcp.wsfe.models import (
    CatalogItem,
    FECAESolicitarRequest,
    FECAESolicitarResponse,
    FECompConsultarRequest,
    FECompConsultarResponse,
    FECompUltimoAutorizadoResponse,
)

# One zeep.Client per WSDL URL — avoids re-downloading/parsing the WSDL on every call.
# Lock guards creation under streamable-http where multiple requests run concurrently.
_wsfe_clients: dict[str, zeep.Client] = {}
_wsfe_clients_lock = threading.Lock()


def _get_wsfe_client(wsdl_url: str) -> zeep.Client:
    if wsdl_url in _wsfe_clients:
        return _wsfe_clients[wsdl_url]
    with _wsfe_clients_lock:
        if wsdl_url not in _wsfe_clients:
            _wsfe_clients[wsdl_url] = zeep.Client(wsdl=wsdl_url)
    return _wsfe_clients[wsdl_url]


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
        client = _get_wsfe_client(wsdl_url)
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


# ---------------------------------------------------------------------------
# Operaciones de emisión y consulta
# ---------------------------------------------------------------------------


def _extract_errors(response, method: str) -> ArcaError | None:
    """Extrae errores del cuerpo de respuesta AFIP; retorna ArcaError o None."""
    errors = getattr(response, "Errors", None)
    if errors is None:
        return None
    error_list = getattr(errors, "Err", None) or []
    if not error_list:
        return None
    msgs = "; ".join(
        f"[{getattr(e, 'Code', '?')}] {getattr(e, 'Msg', '')}"
        for e in error_list
    )
    return ArcaError(
        cause=ArcaErrorCause.ARCA_SERVICE_ERROR,
        message=f"WSFEv1 error en {method}: {msgs}",
    )


def fecae_solicitar(
    token: str,
    sign: str,
    environment: str,
    request: FECAESolicitarRequest,
) -> Union[FECAESolicitarResponse, ArcaError]:
    """Solicita autorización CAE para un comprobante mediante FECAESolicitar.

    Solo disponible en homologación — el ambiente 'produccion' retorna ArcaError.
    Retorna FECAESolicitarResponse con el CAE otorgado o ArcaError si falla.
    """
    if environment == "produccion":
        return ArcaError(
            cause=ArcaErrorCause.UNSUPPORTED_ENVIRONMENT,
            message="fecae_solicitar solo está habilitado en homologación.",
        )

    auth = _build_auth(token, sign, request.cuit)
    if isinstance(auth, ArcaError):
        return auth

    wsdl_url = _wsdl_url(environment)

    # Construir el detalle del comprobante en el formato que espera WSFEv1
    fe_cab_req = {
        "CantReg": 1,
        "PtoVta": request.punto_venta,
        "CbteTipo": request.cbte_tipo,
    }

    fe_det_req = {
        "Concepto": request.concepto,
        "DocTipo": request.doc_tipo,
        "DocNro": int(request.cuit_receptor),
        "CbteDesde": 0,  # WSFE asigna el número
        "CbteHasta": 0,
        "CbteFch": request.fecha_cbte,
        "ImpTotal": float(request.imp_total),
        "ImpTotConc": 0,
        "ImpNeto": float(request.imp_neto),
        "ImpOpEx": 0,
        "ImpIVA": float(request.imp_iva),
        "ImpTrib": 0,
        "MonId": "PES",
        "MonCotiz": 1,
        "Iva": {
            "AlicIva": [
                {
                    "Id": int(request.alicuota_id),
                    "BaseImp": float(request.imp_neto),
                    "Importe": float(request.imp_iva),
                }
            ]
        },
    }

    try:
        client = _get_wsfe_client(wsdl_url)
        response = client.service.FECAESolicitar(
            Auth=auth,
            FeCAEReq={
                "FeCabReq": fe_cab_req,
                "FeDetReq": {"FECAEDetRequest": [fe_det_req]},
            },
        )
    except zeep.exceptions.Fault as exc:
        return ArcaError(
            cause=ArcaErrorCause.ARCA_SERVICE_ERROR,
            message=f"WSFEv1 SOAP Fault en FECAESolicitar: {exc.message}",
        )
    except Exception as exc:
        return ArcaError(
            cause=ArcaErrorCause.ARCA_SERVICE_ERROR,
            message=f"Error de comunicación con WSFEv1 (FECAESolicitar): {exc}",
        )

    err = _extract_errors(response, "FECAESolicitar")
    if err:
        return err

    # Extraer el detalle de la respuesta
    fe_det_resp = None
    try:
        fe_det_resp = response.FeDetResp.FECAEDetResponse[0]
    except (AttributeError, IndexError, TypeError):
        pass

    if fe_det_resp is None:
        return ArcaError(
            cause=ArcaErrorCause.ARCA_SERVICE_ERROR,
            message="WSFEv1 FECAESolicitar: respuesta sin FECAEDetResponse",
        )

    resultado = str(getattr(fe_det_resp, "Resultado", "") or "")
    cae = str(getattr(fe_det_resp, "CAE", "") or "")
    cbte_nro = int(getattr(fe_det_resp, "CbteDesde", 0) or 0)
    cae_fch_vto = str(getattr(fe_det_resp, "CAEFchVto", "") or "")

    # Observaciones (pueden estar ausentes)
    obs_list: list[str] = []
    obs_wrapper = getattr(fe_det_resp, "Observaciones", None)
    if obs_wrapper is not None:
        obs_items = getattr(obs_wrapper, "Obs", None) or []
        for obs in obs_items:
            msg = getattr(obs, "Msg", None)
            if msg:
                obs_list.append(str(msg))

    return FECAESolicitarResponse(
        cae=cae,
        cbte_nro=cbte_nro,
        cae_fch_vto=cae_fch_vto,
        resultado=resultado,
        observaciones=obs_list,
    )


def fecomp_ultimo_autorizado(
    token: str,
    sign: str,
    environment: str,
    cuit: str | int,
    punto_venta: int,
    cbte_tipo: int,
) -> Union[FECompUltimoAutorizadoResponse, ArcaError]:
    """Retorna el último número de comprobante autorizado para un tipo y punto de venta.

    Llama a FECompUltimoAutorizado de WSFEv1.
    """
    auth = _build_auth(token, sign, cuit)
    if isinstance(auth, ArcaError):
        return auth

    wsdl_url = _wsdl_url(environment)

    try:
        client = _get_wsfe_client(wsdl_url)
        response = client.service.FECompUltimoAutorizado(
            Auth=auth,
            PtoVta=punto_venta,
            CbteTipo=cbte_tipo,
        )
    except zeep.exceptions.Fault as exc:
        return ArcaError(
            cause=ArcaErrorCause.ARCA_SERVICE_ERROR,
            message=f"WSFEv1 SOAP Fault en FECompUltimoAutorizado: {exc.message}",
        )
    except Exception as exc:
        return ArcaError(
            cause=ArcaErrorCause.ARCA_SERVICE_ERROR,
            message=f"Error de comunicación con WSFEv1 (FECompUltimoAutorizado): {exc}",
        )

    err = _extract_errors(response, "FECompUltimoAutorizado")
    if err:
        return err

    cbte_nro = int(getattr(response, "CbteNro", 0) or 0)
    return FECompUltimoAutorizadoResponse(cbte_nro=cbte_nro)


def fecomp_consultar(
    token: str,
    sign: str,
    environment: str,
    request: FECompConsultarRequest,
) -> Union[FECompConsultarResponse, ArcaError]:
    """Consulta los datos de un comprobante específico mediante FECompConsultar."""
    auth = _build_auth(token, sign, request.cuit)
    if isinstance(auth, ArcaError):
        return auth

    wsdl_url = _wsdl_url(environment)

    try:
        client = _get_wsfe_client(wsdl_url)
        response = client.service.FECompConsultar(
            Auth=auth,
            FeCompConsReq={
                "PtoVta": request.punto_venta,
                "CbteTipo": request.cbte_tipo,
                "CbteNro": request.cbte_nro,
            },
        )
    except zeep.exceptions.Fault as exc:
        return ArcaError(
            cause=ArcaErrorCause.ARCA_SERVICE_ERROR,
            message=f"WSFEv1 SOAP Fault en FECompConsultar: {exc.message}",
        )
    except Exception as exc:
        return ArcaError(
            cause=ArcaErrorCause.ARCA_SERVICE_ERROR,
            message=f"Error de comunicación con WSFEv1 (FECompConsultar): {exc}",
        )

    err = _extract_errors(response, "FECompConsultar")
    if err:
        return err

    result_get = getattr(response, "ResultGet", None)
    if result_get is None:
        return ArcaError(
            cause=ArcaErrorCause.ARCA_SERVICE_ERROR,
            message="WSFEv1 FECompConsultar: respuesta sin ResultGet",
        )

    return FECompConsultarResponse(
        cbte_nro=int(getattr(result_get, "CbteDesde", 0) or 0),
        cbte_tipo=int(getattr(result_get, "CbteTipo", 0) or 0),
        punto_venta=int(getattr(result_get, "PtoVta", 0) or 0),
        cae=str(getattr(result_get, "CodAutorizacion", "") or ""),
        cae_fch_vto=str(getattr(result_get, "FchVto", "") or ""),
        fecha_cbte=str(getattr(result_get, "CbteFch", "") or ""),
        resultado=str(getattr(result_get, "Resultado", "") or ""),
        doc_tipo=int(getattr(result_get, "DocTipo", 0) or 0),
        doc_nro=str(getattr(result_get, "DocNro", "") or ""),
        imp_total=Decimal(str(getattr(result_get, "ImpTotal", "0") or "0")),
        imp_neto=Decimal(str(getattr(result_get, "ImpNeto", "0") or "0")),
        imp_iva=Decimal(str(getattr(result_get, "ImpIVA", "0") or "0")),
    )
