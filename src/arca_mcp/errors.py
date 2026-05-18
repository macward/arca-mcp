from enum import StrEnum

from pydantic import BaseModel


class ArcaErrorCause(StrEnum):
    # Certificados
    CERT_INVALID = "CERT_INVALID"
    CERT_EXPIRED = "CERT_EXPIRED"
    CERT_NOT_YET_VALID = "CERT_NOT_YET_VALID"
    CERT_KEY_MISMATCH = "CERT_KEY_MISMATCH"
    # Private key
    KEY_INVALID = "KEY_INVALID"
    # WSAA
    WSAA_UNREACHABLE = "WSAA_UNREACHABLE"
    WSAA_AUTH_FAILED = "WSAA_AUTH_FAILED"
    # Servicios
    SERVICE_UNAUTHORIZED = "SERVICE_UNAUTHORIZED"
    # Configuración
    MISSING_CONFIG = "MISSING_CONFIG"
    INVALID_CONFIG_OVERRIDE = "INVALID_CONFIG_OVERRIDE"
    UNSUPPORTED_ENVIRONMENT = "UNSUPPORTED_ENVIRONMENT"


class ArcaError(BaseModel):
    cause: ArcaErrorCause
    message: str
