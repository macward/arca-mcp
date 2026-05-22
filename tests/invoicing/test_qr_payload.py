"""Tests for QRPayload model and build_qr_url."""

import base64
import json

import pytest
from pydantic import ValidationError

from arca_mcp.errors import ArcaError, ArcaErrorCause
from arca_mcp.invoicing.qr import QRPayload, build_qr_url

VALID_PAYLOAD = dict(
    fecha="2024-01-15",
    cuit="20123456789",
    ptoVta=1,
    tipoCmp=1,
    nroCmp=1,
    importe=1000.00,
    moneda="PES",
    ctz=1.0,
    tipoDocRec=80,
    nroDocRec="20987654321",
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


def test_build_qr_url_defensive_invalid_cae():
    """build_qr_url returns INVALID_CAE when bypassing model validation."""
    payload = QRPayload.model_construct(codAut="short")
    result = build_qr_url(payload)
    assert isinstance(result, ArcaError)
    assert result.cause == ArcaErrorCause.INVALID_CAE


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
