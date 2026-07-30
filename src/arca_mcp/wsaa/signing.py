import email
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs7

from arca_mcp.certificates import load_certificate, load_private_key


def sign_tra(tra: bytes, cert_path: Path, key_path: Path) -> str:
    """Firma un TRA con CMS/PKCS7 y devuelve el contenido firmado en base64.

    WSAA espera el body firmado como CMS SMIME (sin headers MIME),
    en formato base64 plano.
    """
    cert = load_certificate(cert_path)
    key = load_private_key(key_path)

    signed_smime = (
        pkcs7.PKCS7SignatureBuilder()
        .set_data(tra)
        .add_signer(cert, key, hashes.SHA256())
        .sign(serialization.Encoding.SMIME, [pkcs7.PKCS7Options.Binary])
    )

    # PKCS7SignatureBuilder retorna un mensaje SMIME multipart.
    # WSAA quiere solo el payload firmado (smime.p7s) en base64.
    msg = email.message_from_string(signed_smime.decode("utf-8"))
    for part in msg.walk():
        filename = part.get_filename() or ""
        if filename.startswith("smime.p7"):
            return part.get_payload(decode=False).replace("\n", "").strip()

    raise RuntimeError("No se encontró la parte firmada smime.p7s en el CMS")
