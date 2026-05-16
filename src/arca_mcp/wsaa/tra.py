import datetime
import secrets

from lxml import etree


def build_tra(service: str, ttl_seconds: int = 2400) -> bytes:
    """Construye un Ticket de Requerimiento de Acceso (TRA) para WSAA.

    El TRA es un XML firmado que el cliente envía a WSAA para solicitar
    un token de autenticación contra un servicio ARCA específico.
    """
    now = datetime.datetime.now(datetime.UTC)
    generation = now - datetime.timedelta(seconds=60)
    expiration = now + datetime.timedelta(seconds=ttl_seconds)

    root = etree.Element("loginTicketRequest", version="1.0")

    header = etree.SubElement(root, "header")
    etree.SubElement(header, "uniqueId").text = str(secrets.randbits(31))
    etree.SubElement(header, "generationTime").text = generation.strftime("%Y-%m-%dT%H:%M:%S-00:00")
    etree.SubElement(header, "expirationTime").text = expiration.strftime("%Y-%m-%dT%H:%M:%S-00:00")

    etree.SubElement(root, "service").text = service

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
