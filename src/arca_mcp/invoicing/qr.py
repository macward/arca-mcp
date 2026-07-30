"""QR payload model and URL builder for AFIP RG 4291/2018."""

import base64
import datetime
import io
import json
import re
from typing import Literal

import qrcode
from pydantic import BaseModel, Field, field_validator, model_validator

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
    nroDocRec: int = Field(description="Número de documento del receptor como entero (0 para Consumidor Final)")
    tipoCodAut: Literal["E"] = "E"
    codAut: str = Field(description="CAE de 14 dígitos numéricos")

    @model_validator(mode="after")
    def _derive_nro_doc_rec(self) -> "QRPayload":
        if self.tipoDocRec == 99:
            self.nroDocRec = 0
        return self

    @field_validator("fecha")
    @classmethod
    def _validate_fecha(cls, v: str) -> str:
        try:
            datetime.date.fromisoformat(v)
        except ValueError:
            raise ValueError("fecha must be a valid calendar date in YYYY-MM-DD format") from None
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


class _CompactFloatEncoder(json.JSONEncoder):
    def encode(self, o: object) -> str:
        if isinstance(o, dict):
            o = {k: (int(v) if isinstance(v, float) and v == int(v) else v) for k, v in o.items()}
        return super().encode(o)


def generate_qr_png(payload: QRPayload) -> bytes:
    """Return a PNG image of the QR code for the given payload.

    The QR encodes the ARCA URL and is generated in memory — no disk writes.
    """
    url = build_qr_url(payload)
    img = qrcode.make(url)
    with io.BytesIO() as buf:
        img.save(buf, format="PNG")  # pyright: ignore[reportCallIssue]
        return buf.getvalue()


def build_qr_url(payload: QRPayload) -> str:
    """Return the ARCA QR URL for the given payload.

    Assumes payload has already been validated via the QRPayload constructor.
    codAut is guaranteed to be 14 numeric digits by the model's field_validator.
    """
    data = json.dumps(payload.model_dump(), separators=(",", ":"), cls=_CompactFloatEncoder)
    encoded = base64.urlsafe_b64encode(data.encode()).rstrip(b"=").decode()
    return f"{_QR_BASE}{encoded}"
