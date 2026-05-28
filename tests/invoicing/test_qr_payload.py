"""Tests for QRPayload model and build_qr_url."""

import base64
import json
from typing import Any

import pytest
from pydantic import ValidationError

from arca_mcp.invoicing.qr import QRPayload, build_qr_url

VALID_PAYLOAD: dict[str, Any] = dict(
    fecha="2024-01-15",
    cuit="20123456789",
    ptoVta=1,
    tipoCmp=1,
    nroCmp=1,
    importe=1000.00,
    moneda="PES",
    ctz=1.0,
    tipoDocRec=80,
    nroDocRec=20987654321,
    codAut="12345678901234",
)


def test_valid_payload_construction():
    payload = QRPayload(**VALID_PAYLOAD)
    assert payload.ver == 1
    assert payload.tipoCodAut == "E"
    assert payload.codAut == "12345678901234"


def test_invalid_fecha_format():
    with pytest.raises(ValidationError):
        QRPayload(**{**VALID_PAYLOAD, "fecha": "15/01/2024"})


def test_invalid_fecha_out_of_range():
    with pytest.raises(ValidationError):
        QRPayload(**{**VALID_PAYLOAD, "fecha": "2024-99-99"})


def test_invalid_cuit_length():
    with pytest.raises(ValidationError):
        QRPayload(**{**VALID_PAYLOAD, "cuit": "123456"})


def test_cae_short_raises_validation_error():
    with pytest.raises(ValidationError):
        QRPayload(**{**VALID_PAYLOAD, "codAut": "1234567890"})  # 10 digits


def test_cae_non_numeric_raises_validation_error():
    with pytest.raises(ValidationError):
        QRPayload(**{**VALID_PAYLOAD, "codAut": "1234567890123X"})



def test_valid_url_decodes_to_original_json():
    payload = QRPayload(**VALID_PAYLOAD)
    url = build_qr_url(payload)
    assert isinstance(url, str)
    assert url.startswith("https://www.arca.gob.ar/fe/qr/?p=")

    b64 = url.split("?p=")[1]
    decoded = json.loads(base64.urlsafe_b64decode(b64 + "==").decode())
    assert decoded["codAut"] == VALID_PAYLOAD["codAut"]
    assert decoded["cuit"] == VALID_PAYLOAD["cuit"]
    assert decoded["tipoCodAut"] == "E"


def test_nro_doc_rec_consumidor_final_is_zero():
    """doc_tipo=99 (Consumidor Final) must force nroDocRec to 0."""
    payload = QRPayload(**{**VALID_PAYLOAD, "tipoDocRec": 99, "nroDocRec": 20123456789})
    assert payload.nroDocRec == 0


def test_nro_doc_rec_cuit_uses_receptor_value():
    """doc_tipo=80 (CUIT) must preserve the provided nroDocRec as int."""
    cuit_receptor = 20987654321
    payload = QRPayload(**{**VALID_PAYLOAD, "tipoDocRec": 80, "nroDocRec": cuit_receptor})
    assert payload.nroDocRec == cuit_receptor


def test_nro_doc_rec_dni_uses_receptor_value():
    """doc_tipo=96 (DNI) must preserve the provided nroDocRec as int."""
    dni = 30123456
    payload = QRPayload(**{**VALID_PAYLOAD, "tipoDocRec": 96, "nroDocRec": dni})
    assert payload.nroDocRec == dni


def _decode_qr_json(url: str) -> dict:
    b64 = url.split("?p=")[1]
    return json.loads(base64.urlsafe_b64decode(b64 + "==").decode())


def test_importe_whole_float_serializes_without_decimals():
    payload = QRPayload(**{**VALID_PAYLOAD, "importe": 1000.0})
    url = build_qr_url(payload)
    assert isinstance(url, str)
    raw = base64.urlsafe_b64decode(url.split("?p=")[1] + "==").decode()
    assert '"importe":1000' in raw
    assert '"importe":1000.' not in raw


def test_importe_fractional_float_serializes_with_decimals():
    payload = QRPayload(**{**VALID_PAYLOAD, "importe": 1000.5})
    url = build_qr_url(payload)
    assert isinstance(url, str)
    decoded = _decode_qr_json(url)
    assert decoded["importe"] == 1000.5
