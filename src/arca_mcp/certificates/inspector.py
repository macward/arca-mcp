from pathlib import Path

from cryptography.x509.oid import NameOID

from arca_mcp.certificates.errors import CertificateLoadError
from arca_mcp.certificates.loader import load_certificate
from arca_mcp.certificates.models import CertificateInspection, CertificateValidationResult
from arca_mcp.errors import ArcaErrorCause


def inspect_certificate(path: Path) -> CertificateInspection | CertificateValidationResult:
    try:
        cert = load_certificate(path)
    except CertificateLoadError as e:
        return CertificateValidationResult(valid=False, cause=ArcaErrorCause.CERT_INVALID, message=str(e))

    def get_attr(name, oid):
        try:
            return name.get_attributes_for_oid(oid)[0].value
        except IndexError:
            return None

    subject = cert.subject
    issuer = cert.issuer

    return CertificateInspection(
        common_name=get_attr(subject, NameOID.COMMON_NAME),
        organization=get_attr(subject, NameOID.ORGANIZATION_NAME),
        issuer_common_name=get_attr(issuer, NameOID.COMMON_NAME),
        issuer_organization=get_attr(issuer, NameOID.ORGANIZATION_NAME),
        serial_number=str(cert.serial_number),
        not_valid_before=cert.not_valid_before_utc.isoformat(),
        not_valid_after=cert.not_valid_after_utc.isoformat(),
        is_self_signed=cert.issuer == cert.subject,
    )
