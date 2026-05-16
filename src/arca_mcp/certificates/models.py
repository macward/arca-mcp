from pydantic import BaseModel

from arca_mcp.errors import ArcaErrorCause


class CertificateValidationResult(BaseModel):
    valid: bool
    cause: ArcaErrorCause | None = None
    message: str | None = None


class CertificateInspection(BaseModel):
    common_name: str | None
    organization: str | None
    issuer_common_name: str | None
    issuer_organization: str | None
    serial_number: str
    not_valid_before: str
    not_valid_after: str
    is_self_signed: bool
