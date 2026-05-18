import datetime
from pathlib import Path

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from arca_mcp.certificates.errors import CertificateLoadError, PrivateKeyLoadError
from arca_mcp.certificates.loader import load_certificate, load_private_key
from arca_mcp.certificates.models import CertificateValidationResult
from arca_mcp.errors import ArcaErrorCause


def validate_certificate(path: Path) -> CertificateValidationResult:
    try:
        cert = load_certificate(path)
    except CertificateLoadError as e:
        return CertificateValidationResult(valid=False, cause=ArcaErrorCause.CERT_INVALID, message=str(e))
    except Exception as e:
        return CertificateValidationResult(
            valid=False,
            cause=ArcaErrorCause.CERT_INVALID,
            message=f"Error inesperado al cargar certificado ({type(e).__name__}): {e}",
        )

    now = datetime.datetime.now(datetime.UTC)

    if now < cert.not_valid_before_utc:
        return CertificateValidationResult(
            valid=False,
            cause=ArcaErrorCause.CERT_NOT_YET_VALID,
            message=f"El certificado no es válido hasta {cert.not_valid_before_utc.isoformat()}",
        )

    if now > cert.not_valid_after_utc:
        return CertificateValidationResult(
            valid=False,
            cause=ArcaErrorCause.CERT_EXPIRED,
            message=f"El certificado venció el {cert.not_valid_after_utc.isoformat()}",
        )

    return CertificateValidationResult(valid=True)


def validate_private_key(path: Path) -> CertificateValidationResult:
    try:
        load_private_key(path)
    except PrivateKeyLoadError as e:
        return CertificateValidationResult(valid=False, cause=ArcaErrorCause.KEY_INVALID, message=str(e))
    except Exception as e:
        return CertificateValidationResult(
            valid=False,
            cause=ArcaErrorCause.KEY_INVALID,
            message=f"Error inesperado al cargar private key ({type(e).__name__}): {e}",
        )

    return CertificateValidationResult(valid=True)


def validate_cert_key_match(cert_path: Path, key_path: Path) -> CertificateValidationResult:
    try:
        cert = load_certificate(cert_path)
    except CertificateLoadError as e:
        return CertificateValidationResult(valid=False, cause=ArcaErrorCause.CERT_INVALID, message=str(e))
    except Exception as e:
        return CertificateValidationResult(
            valid=False,
            cause=ArcaErrorCause.CERT_INVALID,
            message=f"Error inesperado al cargar certificado ({type(e).__name__}): {e}",
        )

    try:
        key = load_private_key(key_path)
    except PrivateKeyLoadError as e:
        return CertificateValidationResult(valid=False, cause=ArcaErrorCause.KEY_INVALID, message=str(e))
    except Exception as e:
        return CertificateValidationResult(
            valid=False,
            cause=ArcaErrorCause.KEY_INVALID,
            message=f"Error inesperado al cargar private key ({type(e).__name__}): {e}",
        )

    try:
        cert_pub = cert.public_key().public_bytes(
            encoding=Encoding.PEM,
            format=PublicFormat.SubjectPublicKeyInfo,
        )
        key_pub = key.public_key().public_bytes(
            encoding=Encoding.PEM,
            format=PublicFormat.SubjectPublicKeyInfo,
        )
    except Exception as e:
        return CertificateValidationResult(
            valid=False,
            cause=ArcaErrorCause.CERT_KEY_MISMATCH,
            message=f"No se pudo comparar las claves públicas ({type(e).__name__}): {e}",
        )

    if cert_pub != key_pub:
        return CertificateValidationResult(
            valid=False,
            cause=ArcaErrorCause.CERT_KEY_MISMATCH,
            message="El certificado no corresponde a la private key",
        )

    return CertificateValidationResult(valid=True)
