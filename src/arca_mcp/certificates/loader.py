from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key

from arca_mcp.certificates.errors import CertificateLoadError, PrivateKeyLoadError


def load_certificate(path: Path) -> x509.Certificate:
    try:
        pem_data = path.read_bytes()
    except FileNotFoundError:
        raise CertificateLoadError(f"Archivo no encontrado: {path}")
    except OSError as e:
        raise CertificateLoadError(f"Error leyendo archivo: {e}")

    try:
        return x509.load_pem_x509_certificate(pem_data)
    except Exception as e:
        raise CertificateLoadError(f"Certificado inválido o corrompido: {e}")


def load_private_key(path: Path) -> RSAPrivateKey:
    try:
        pem_data = path.read_bytes()
    except FileNotFoundError:
        raise PrivateKeyLoadError(f"Archivo no encontrado: {path}")
    except OSError as e:
        raise PrivateKeyLoadError(f"Error leyendo archivo: {e}")

    try:
        key = load_pem_private_key(pem_data, password=None)
    except Exception as e:
        raise PrivateKeyLoadError(f"Private key inválida o corrompida: {e}")

    if not isinstance(key, RSAPrivateKey):
        raise PrivateKeyLoadError(f"Tipo de key no soportado: {type(key).__name__}. Se requiere RSA.")

    return key
