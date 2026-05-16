from enum import StrEnum


class ArcaService(StrEnum):
    """Servicios ARCA/AFIP conocidos para autenticación WSAA.

    El cliente puede pasar un string arbitrario también; este enum es
    para autocompletar y validación de los servicios más comunes.
    """
    WSFE = "wsfe"                          # Factura Electrónica
    WSFEX = "wsfex"                        # Factura Electrónica de Exportación
    WSMTXCA = "wsmtxca"                    # Factura Electrónica con detalle
    WS_SR_PADRON_A4 = "ws_sr_padron_a4"    # Padrón nivel 4
    WS_SR_PADRON_A5 = "ws_sr_padron_a5"    # Padrón nivel 5
    WS_SR_PADRON_A13 = "ws_sr_padron_a13"  # Padrón nivel 13
    WSBFEV1 = "wsbfev1"                    # Bono Fiscal Electrónico
    WSCTG = "wsctg"                        # Código de Trazabilidad de Granos
    WSLPG = "wslpg"                        # Liquidación Primaria de Granos
    WSREMCARNE = "wsremcarne"              # Remito Electrónico Cárnico
    WSREMHARINA = "wsremharina"            # Remito Electrónico Harinero
    WSREMAZUCAR = "wsremazucar"            # Remito Electrónico Azúcar
    WSCPE = "wscpe"                        # Carta de Porte Electrónica
