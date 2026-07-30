from typing import Optional

from pydantic import BaseModel


class FiscalAddress(BaseModel):
    street: Optional[str] = None
    number: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    zip_code: Optional[str] = None


class PersonaDetails(BaseModel):
    cuit: str
    denomination: str          # razonSocial o apellido + nombre
    status: str                # estadoClave: "ACTIVO", "INACTIVO", etc.
    fiscal_address: Optional[FiscalAddress] = None
    activities: list[str] = []  # códigos de actividad AFIP


class TaxpayerStatus(BaseModel):
    cuit: str
    active: bool
    status_description: str
