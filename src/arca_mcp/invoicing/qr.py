"""QR payload model and URL builder for AFIP RG 4291/2018."""

import base64
import datetime
import io
import json
import re
from typing import Literal

import qrcode
from pydantic import BaseModel, Field, field_validator

from arca_mcp.errors import ArcaError, ArcaErrorCause

_CAE_RE = re.compile(r"^\d{14}$")
_CUIT_RE = re.compile(r"^\d{11}$")

_QR_BASE = "https://www.arca.gob.ar/fe/qr/?p="


class QRPayload(BaseModel):
    ver: Literal[1] = 1
    fecha: str = Field(description="Fecha RFC3339 YYYY-MM-DD")
    cuit: str = Field(description="CUIT del emisor, 11 dígitos")
    ptoVta: int
    tipoCmp: int
    nroCmp: int
    importe: float
    moneda: str
    ctz: float
    tipoDocRec: int
    nroDocRec: str = Field(description="Número de documento del receptor (1-11 dígitos, o '0' para consumidor final)")
    tipoCodAut: Literal["E"] = "E"
    codAut: str = Field(description="CAE de 14 dígitos numéricos")

    @field_validator("fecha")
    @classmethod
    def _validate_fecha(cls, v: str) -> str:
        try:
            datetime.date.fromisoformat(v)
        except ValueError:
            raise ValueError("fecha must be a valid calendar date in YYYY-MM-DD format")
        return v

    @field_validator("cuit")
    @classmethod
    def _validate_cuit(cls, v: str) -> str:
        if not _CUIT_RE.match(v):
            raise ValueError("cuit must be 11 digits")
        return v

    @field_validator("codAut")
    @classmethod
    def _validate_cod_aut(cls, v: str) -> str:
        if not _CAE_RE.match(v):
            raise ValueError("codAut must be exactly 14 numeric digits")
        return v


def generate_qr_png(payload: QRPayload) -> bytes:
    """Return a PNG image of the QR code for the given payload.

    The QR encodes the ARCA URL and is generated in memory — no disk writes.
    """
    url = build_qr_url(payload)
    if isinstance(url, ArcaError):
        raise ValueError(url.message)
    img = qrcode.make(url)
    with io.BytesIO() as buf:
        img.save(buf, format="PNG")
        return buf.getvalue()


def build_qr_url(payload: QRPayload) -> str | ArcaError:
    """Return the ARCA QR URL for the given payload.

    Returns ArcaError(INVALID_CAE) if codAut is not 14 numeric digits.
    Validation at the model level should catch this first, but this
    provides a defensive check for callers that bypass model validation.
    """
    if not _CAE_RE.match(payload.codAut):
        return ArcaError(
            cause=ArcaErrorCause.INVALID_CAE,
            message=f"codAut must be exactly 14 numeric digits, got: '{payload.codAut}'",
        )
    data = json.dumps(payload.model_dump(), separators=(",", ":"))
    encoded = base64.urlsafe_b64encode(data.encode()).rstrip(b"=").decode()
    return f"{_QR_BASE}{encoded}"
