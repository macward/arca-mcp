"""PDF renderer for confirmed AFIP vouchers."""

import io
import re
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from arca_mcp.invoicing.qr import QRPayload, generate_qr_png
from arca_mcp.validation.catalogs import IVA_ALIQUOTS

_CAE_RE = re.compile(r"^\d{14}$")
_CUIT_RE = re.compile(r"^\d{11}$")

_CBTE_LETTER: dict[int, str] = {
    1: "A", 2: "A", 3: "A",
    6: "B", 7: "B", 8: "B",
    11: "C", 12: "C", 13: "C",
    51: "M", 52: "M", 53: "M",
}

def _aliquot_label(alicuota_id: str) -> str:
    rate = IVA_ALIQUOTS.get(alicuota_id)
    if rate is None:
        return alicuota_id
    pct = rate * 100
    return f"{pct:g}%"


class ConfirmedVoucherInput(BaseModel):
    # Voucher header
    cbte_tipo: int
    punto_venta: int
    cbte_nro: int
    fecha_cbte: str = Field(pattern=r"^\d{8}$", description="YYYYMMDD")

    # CAE data
    cae: str = Field(description="CAE de 14 dígitos numéricos")
    cae_fch_vto: str = Field(pattern=r"^\d{8}$", description="Fecha de vencimiento CAE YYYYMMDD")

    # Currency
    moneda: str = Field(default="PES")
    ctz: float = Field(default=1.0)

    # Amounts
    imp_neto: Decimal = Field(ge=Decimal("0"))
    alicuota_id: str

    # Emisor
    cuit_emisor: str = Field(description="CUIT del emisor, 11 dígitos")
    emisor_razon_social: str
    emisor_domicilio: str

    # Receptor
    cuit_receptor: str = Field(description="CUIT del receptor, 11 dígitos")
    doc_tipo: int = Field(description="Tipo de documento del receptor")
    nro_doc_receptor: Optional[str] = Field(
        default=None,
        description=(
            "Número de documento del receptor para el QR. "
            "Auto-derivado si es None: doc_tipo=80 → cuit_receptor, doc_tipo=99 → '0'. "
            "Requerido explícitamente para otros doc_tipo (DNI, pasaporte, etc.)."
        ),
    )
    receptor_razon_social: Optional[str] = None

    @field_validator("cae")
    @classmethod
    def _validate_cae(cls, v: str) -> str:
        if not _CAE_RE.match(v):
            raise ValueError("cae must be exactly 14 numeric digits")
        return v

    @field_validator("cuit_emisor", "cuit_receptor")
    @classmethod
    def _validate_cuit(cls, v: str) -> str:
        if not _CUIT_RE.match(v):
            raise ValueError("cuit must be 11 digits")
        return v

    @model_validator(mode="after")
    def _derive_nro_doc_receptor(self) -> "ConfirmedVoucherInput":
        if self.nro_doc_receptor is not None:
            return self
        if self.doc_tipo == 80:
            self.nro_doc_receptor = self.cuit_receptor
        elif self.doc_tipo == 99:
            self.nro_doc_receptor = "0"
        else:
            raise ValueError(
                f"nro_doc_receptor is required for doc_tipo={self.doc_tipo}. "
                "Provide the receptor's document number explicitly "
                "(e.g. DNI number for doc_tipo=96)."
            )
        return self

    @field_validator("alicuota_id")
    @classmethod
    def _validate_alicuota(cls, v: str) -> str:
        if v not in IVA_ALIQUOTS:
            valid = ", ".join(sorted(IVA_ALIQUOTS))
            raise ValueError(f"alicuota_id '{v}' not valid. Valid: {valid}")
        return v

    @property
    def imp_iva(self) -> Decimal:
        rate = IVA_ALIQUOTS.get(self.alicuota_id, Decimal("0"))
        return (self.imp_neto * rate).quantize(Decimal("0.01"))

    @property
    def imp_total(self) -> Decimal:
        return (self.imp_neto + self.imp_iva).quantize(Decimal("0.01"))


def _fecha_display(yyyymmdd: str) -> str:
    return f"{yyyymmdd[6:8]}/{yyyymmdd[4:6]}/{yyyymmdd[:4]}"


def _cbte_letter(cbte_tipo: int) -> str:
    return _CBTE_LETTER.get(cbte_tipo, " ")


def generate_invoice_pdf(voucher: ConfirmedVoucherInput) -> bytes:
    """Render a PDF for the given confirmed voucher. Returns PDF bytes."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )
    styles = getSampleStyleSheet()
    story = []

    letter = _cbte_letter(voucher.cbte_tipo)

    # Header table: letter box | voucher info
    header_data = [
        [
            Paragraph(f"<b>{letter}</b>", styles["Title"]),
            Paragraph(
                f"Comprobante tipo {voucher.cbte_tipo}<br/>"
                f"Punto de Venta: <b>{voucher.punto_venta:05d}</b><br/>"
                f"N°: <b>{voucher.cbte_nro:08d}</b><br/>"
                f"Fecha: {_fecha_display(voucher.fecha_cbte)}",
                styles["Normal"],
            ),
        ]
    ]
    header_table = Table(header_data, colWidths=[3 * cm, None])
    header_table.setStyle(
        TableStyle([
            ("BOX", (0, 0), (-1, -1), 1, colors.black),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("FONTSIZE", (0, 0), (0, -1), 28),
        ])
    )
    story.append(header_table)
    story.append(Spacer(1, 0.4 * cm))

    # Emisor / Receptor
    party_data = [
        [
            Paragraph(
                f"<b>Emisor:</b> {voucher.emisor_razon_social}<br/>"
                f"CUIT: {voucher.cuit_emisor}<br/>"
                f"Domicilio: {voucher.emisor_domicilio}",
                styles["Normal"],
            ),
            Paragraph(
                f"<b>Receptor:</b> {voucher.receptor_razon_social or 'Consumidor Final'}<br/>"
                f"CUIT: {voucher.cuit_receptor}",
                styles["Normal"],
            ),
        ]
    ]
    party_table = Table(party_data, colWidths=["50%", "50%"])
    party_table.setStyle(
        TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ])
    )
    story.append(party_table)
    story.append(Spacer(1, 0.4 * cm))

    # Items table
    alq_label = _aliquot_label(voucher.alicuota_id)
    items_data = [
        ["Concepto", "Importe Neto", f"IVA ({alq_label})", "Total"],
        [
            "Servicio/Producto",
            f"$ {voucher.imp_neto:,.2f}",
            f"$ {voucher.imp_iva:,.2f}",
            f"$ {voucher.imp_total:,.2f}",
        ],
    ]
    items_table = Table(items_data, colWidths=["40%", "20%", "20%", "20%"])
    items_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ])
    )
    story.append(items_table)
    story.append(Spacer(1, 0.4 * cm))

    # CAE box + QR side by side
    qr_payload = QRPayload(
        fecha=f"{voucher.fecha_cbte[:4]}-{voucher.fecha_cbte[4:6]}-{voucher.fecha_cbte[6:8]}",
        cuit=voucher.cuit_emisor,
        ptoVta=voucher.punto_venta,
        tipoCmp=voucher.cbte_tipo,
        nroCmp=voucher.cbte_nro,
        importe=float(voucher.imp_total),
        moneda=voucher.moneda,
        ctz=voucher.ctz,
        tipoDocRec=voucher.doc_tipo,
        nroDocRec=voucher.nro_doc_receptor,  # type: ignore[arg-type]  # always set by model_validator
        codAut=voucher.cae,
    )
    qr_bytes = generate_qr_png(qr_payload)
    qr_image = Image(io.BytesIO(qr_bytes), width=3 * cm, height=3 * cm)

    cae_data = [
        [
            Paragraph(
                f"<b>CAE:</b> {voucher.cae}<br/>"
                f"<b>Vencimiento CAE:</b> {_fecha_display(voucher.cae_fch_vto)}",
                styles["Normal"],
            ),
            qr_image,
        ]
    ]
    cae_table = Table(cae_data, colWidths=[None, 3.5 * cm])
    cae_table.setStyle(
        TableStyle([
            ("BOX", (0, 0), (-1, -1), 1, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ])
    )
    story.append(cae_table)

    doc.build(story)
    return buf.getvalue()
