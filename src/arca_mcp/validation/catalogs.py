"""Catálogos hardcodeados de AFIP para validaciones puras sin red."""

from __future__ import annotations

# Tipos de comprobante más comunes (IVA Responsable Inscripto)
INVOICE_TYPES: frozenset[str] = frozenset({
    "1",   # Factura A
    "2",   # Nota de Débito A
    "3",   # Nota de Crédito A
    "6",   # Factura B
    "7",   # Nota de Débito B
    "8",   # Nota de Crédito B
    "11",  # Factura C
    "12",  # Nota de Débito C
    "13",  # Nota de Crédito C
    "51",  # Factura M
    "52",  # Nota de Débito M
    "53",  # Nota de Crédito M
})

# Condiciones frente al IVA
VAT_CONDITIONS: frozenset[str] = frozenset({
    "1",   # IVA Responsable Inscripto
    "2",   # IVA Responsable No Inscripto
    "3",   # IVA No Responsable
    "4",   # IVA Sujeto Exento
    "5",   # Consumidor Final
    "6",   # Responsable Monotributo
    "7",   # Sujeto No Categorizado
    "8",   # Importador del Exterior
    "9",   # Cliente del Exterior
    "10",  # IVA Liberado – Ley Nº 19.640
    "13",  # Monotributista Social
    "16",  # IVA No Alcanzado
})

# Monedas más comunes
CURRENCIES: frozenset[str] = frozenset({
    "PES",  # Pesos Argentinos
    "DOL",  # Dólar Estadounidense
    "EUR",  # Euro
    "BRL",  # Real Brasileño
    "012",  # Dólar Libre EEUU
})


def is_valid_invoice_type(invoice_type: str) -> bool:
    """Retorna True si el tipo de comprobante existe en el catálogo AFIP."""
    return invoice_type in INVOICE_TYPES


def is_valid_vat_condition(vat_condition: str) -> bool:
    """Retorna True si la condición frente al IVA existe en el catálogo AFIP."""
    return vat_condition in VAT_CONDITIONS


def is_valid_currency(currency: str) -> bool:
    """Retorna True si el código de moneda existe en el catálogo AFIP."""
    return currency in CURRENCIES
