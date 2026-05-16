# MCP ARCA — v0 Setup Doctor — Documento Técnico

> Documento técnico completo de la entrega v0. Para versión no técnica ver `v0_resumen_ejecutivo.md`.

## Índice

1. [Stack y dependencias](#stack-y-dependencias)
2. [Arquitectura general](#arquitectura-general)
3. [Estructura de módulos](#estructura-de-módulos)
4. [Capa de errores estructurados](#capa-de-errores-estructurados)
5. [Módulo `certificates/`](#módulo-certificates)
6. [Módulo `wsaa/`](#módulo-wsaa)
7. [Tools MCP](#tools-mcp)
8. [Setup Doctor — orquestador](#setup-doctor--orquestador)
9. [Testing](#testing)
10. [Infraestructura y Docker](#infraestructura-y-docker)
11. [Decisiones técnicas clave](#decisiones-técnicas-clave)
12. [Métricas](#métricas)

---

## Stack y dependencias

| Categoría | Tecnología | Versión | Uso |
|---|---|---|---|
| Lenguaje | Python | 3.12+ | Base |
| MCP framework | FastMCP | 3.3.1 | Servidor MCP + transporte stdio/HTTP |
| Crypto | cryptography | ≥43.0 | X509 parsing, RSA, PKCS7/CMS signing |
| HTTP | httpx | ≥0.27 | POST SOAP a WSAA |
| XML | lxml | ≥5.0 | Construcción/parseo TRA y respuestas SOAP |
| Validación | pydantic | ≥2.0 | Modelos de datos |
| Config | pydantic-settings | ≥2.0 | Settings via env vars |
| Build | hatchling | — | Empaquetado |
| Tests | pytest + pytest-mock | — | Unit tests |

**Sin** `pyafipws`, **sin** `pysimplesoap`, **sin** `zeep`. Implementación de WSAA hecha desde cero (ver [decisiones técnicas](#decisiones-técnicas-clave)).

---

## Arquitectura general

Capas separadas con dirección de dependencias estricta:

```
┌─────────────────────────────────────────────┐
│  MCP Server (FastMCP)                       │
│  src/arca_mcp/server.py                     │
│  mounts: certificates, setup                │
└────────────────┬────────────────────────────┘
                 │
┌────────────────▼────────────────────────────┐
│  Tools MCP (capa pública)                   │
│  src/arca_mcp/mcp/{certificates,setup}.py   │
│  - Reciben strings, devuelven Pydantic      │
└────────────────┬────────────────────────────┘
                 │
┌────────────────▼────────────────────────────┐
│  Lógica de dominio                          │
│  src/arca_mcp/certificates/ + wsaa/         │
│  - Pure functions, sin I/O de red salvo wsaa│
└────────────────┬────────────────────────────┘
                 │
┌────────────────▼────────────────────────────┐
│  Capa transversal                           │
│  errors.py (StrEnum + Pydantic)             │
│  error_mapping.py (excepciones → ArcaError) │
└─────────────────────────────────────────────┘
```

**Reglas de capa:**

- `mcp/*` solo importa de `certificates/`, `wsaa/`, `errors`
- `wsaa/` puede importar de `certificates/`
- `certificates/` no importa de nadie del proyecto (salvo `errors` global)
- Los tipos de error (`ArcaErrorCause`) están en un módulo separado del mapper (`error_mapping`) para evitar circular imports

---

## Estructura de módulos

```
src/arca_mcp/
├── __init__.py          # version
├── server.py            # entry point FastMCP, mount de subservers
├── config.py            # Settings + Environment enum (homologación/producción)
├── errors.py            # ArcaErrorCause (StrEnum), ArcaError (Pydantic)
├── error_mapping.py     # wrap_error(): Exception → ArcaError
│
├── mcp/                 # Tools MCP (capa pública)
│   ├── __init__.py
│   ├── certificates.py  # 4 tools: validate_cert, validate_key, match, inspect
│   └── setup.py         # 3 tools: wsaa_login, service_auth, setup_doctor
│
├── certificates/        # Manejo X509 + RSA
│   ├── __init__.py
│   ├── loader.py        # load_certificate, load_private_key (I/O PEM)
│   ├── validator.py     # validate_certificate, validate_private_key, validate_cert_key_match
│   ├── inspector.py     # inspect_certificate (metadata)
│   ├── models.py        # CertificateValidationResult, CertificateInspection
│   └── errors.py        # CertificateLoadError, PrivateKeyLoadError
│
├── wsaa/                # Autenticación AFIP
│   ├── __init__.py
│   ├── tra.py           # build_tra(): genera XML del Ticket de Requerimiento
│   ├── signing.py       # sign_tra(): firma CMS/PKCS7 → base64
│   ├── client.py        # call_login_cms (httpx) + parse_login_ticket_response
│   ├── login.py         # validate_wsaa_login, validate_service_authorization
│   ├── doctor.py        # run_setup_doctor (orquestador con short-circuit)
│   ├── services.py      # ArcaService (StrEnum con 13 servicios conocidos)
│   └── models.py        # SetupCheckResult, WsaaToken
│
├── arca/                # [v2] Lógica fiscal pura
├── policy/              # [v3] Reglas de validación de comprobantes
├── validation/          # [v3] Validaciones fiscales (CUIT, IVA)
├── audit/               # [v3] Logging de operaciones irreversibles
└── playwright/          # [v4] Automatización portal ARCA
```

Los módulos vacíos están reservados para fases futuras (`__init__.py` vacío como marcador).

---

## Capa de errores estructurados

### `ArcaErrorCause` (StrEnum)

Catálogo cerrado de causas de error que pueden aparecer en cualquier respuesta MCP:

```python
class ArcaErrorCause(StrEnum):
    # Certificados
    CERT_INVALID
    CERT_EXPIRED
    CERT_NOT_YET_VALID
    CERT_KEY_MISMATCH
    # Private key
    KEY_INVALID
    # WSAA
    WSAA_UNREACHABLE
    WSAA_AUTH_FAILED
    # Servicios
    SERVICE_UNAUTHORIZED
```

Es `StrEnum` para serializar transparente a JSON en las respuestas MCP.

### `ArcaError` (Pydantic)

```python
class ArcaError(BaseModel):
    cause: ArcaErrorCause
    message: str
```

### `wrap_error(exc)` — mapper de excepciones

```python
# arca_mcp/error_mapping.py
def wrap_error(exc: Exception) -> ArcaError:
    if isinstance(exc, CertificateLoadError):
        return ArcaError(cause=CERT_INVALID, message=str(exc))
    if isinstance(exc, PrivateKeyLoadError):
        return ArcaError(cause=KEY_INVALID, message=str(exc))
    if isinstance(exc, (TimeoutError, ConnectionError, socket.gaierror)):
        return ArcaError(cause=WSAA_UNREACHABLE, message=...)
    return ArcaError(cause=WSAA_AUTH_FAILED, message=f"{type(exc).__name__}: ...")
```

**Por qué separamos `errors.py` y `error_mapping.py`:** el mapper necesita importar de `certificates.errors`, y `certificates.models` importa de `errors.py`. Si el mapper viviera en `errors.py` se generaría un circular import.

---

## Módulo `certificates/`

### Loader (`loader.py`)

I/O puro de archivos PEM. Sin lógica de validación.

```python
def load_certificate(path: Path) -> x509.Certificate
def load_private_key(path: Path) -> RSAPrivateKey
```

Errores específicos:
- `FileNotFoundError` → `CertificateLoadError("Archivo no encontrado: ...")`
- `OSError` → `CertificateLoadError("Error leyendo archivo: ...")`
- Parse fail → `CertificateLoadError("Certificado inválido o corrompido: ...")`
- Tipo de key ≠ RSA → `PrivateKeyLoadError("Tipo de key no soportado: ... Se requiere RSA.")`

### Validator (`validator.py`)

#### `validate_certificate(path) → CertificateValidationResult`

1. Cargar via loader
2. Comparar `not_valid_before_utc` y `not_valid_after_utc` contra `datetime.now(UTC)`
3. Mapear a `CERT_INVALID`, `CERT_NOT_YET_VALID`, `CERT_EXPIRED`

#### `validate_private_key(path) → CertificateValidationResult`

Solo intenta cargar; si falla → `KEY_INVALID`.

#### `validate_cert_key_match(cert_path, key_path) → CertificateValidationResult`

1. Cargar cert y key
2. Serializar ambas public keys a PEM con formato `SubjectPublicKeyInfo`
3. Comparar bytes
4. Si difieren → `CERT_KEY_MISMATCH`

Esta comparación funciona con cualquier algoritmo (RSA, EC) porque comparamos la representación canónica de la public key.

### Inspector (`inspector.py`)

#### `inspect_certificate(path) → CertificateInspection | CertificateValidationResult`

Extrae metadata legible del certificado:

```python
class CertificateInspection(BaseModel):
    common_name: str | None
    organization: str | None
    issuer_common_name: str | None
    issuer_organization: str | None
    serial_number: str
    not_valid_before: str   # ISO 8601
    not_valid_after: str    # ISO 8601
    is_self_signed: bool    # subject == issuer
```

Si el cert no se puede cargar, retorna `CertificateValidationResult(valid=False, cause=CERT_INVALID)` — union type explícito para que el caller distinga éxito de error.

---

## Módulo `wsaa/`

### Flujo completo de autenticación WSAA

```
┌──────────────────────────────────────────────────────────────┐
│  cert_path, key_path, service                                │
└──────────────────────────────────────────────────────────────┘
                  │
                  ▼
┌──────────────────────────────────────────────────────────────┐
│  build_tra(service)                              [tra.py]    │
│  → bytes del XML loginTicketRequest:                         │
│    <loginTicketRequest version="1.0">                        │
│      <header>                                                │
│        <uniqueId>{random 31-bit int}</uniqueId>              │
│        <generationTime>now - 60s</generationTime>            │
│        <expirationTime>now + 2400s</expirationTime>          │
│      </header>                                               │
│      <service>{service}</service>                            │
│    </loginTicketRequest>                                     │
└──────────────────────────────────────────────────────────────┘
                  │
                  ▼
┌──────────────────────────────────────────────────────────────┐
│  sign_tra(tra, cert, key)                        [signing.py]│
│  1. Load cert + key                                          │
│  2. PKCS7SignatureBuilder con SHA256                         │
│  3. Output SMIME (no detached, binary)                       │
│  4. Extrae smime.p7s del multipart                           │
│  5. Devuelve string base64 sin headers MIME                  │
└──────────────────────────────────────────────────────────────┘
                  │
                  ▼
┌──────────────────────────────────────────────────────────────┐
│  call_login_cms(cms_b64, endpoint)               [client.py] │
│  POST a https://wsaahomo.afip.gov.ar/ws/services/LoginCms    │
│  Body: SOAP envelope con <wsaa:loginCms><wsaa:in0>{cms}      │
│  Headers: Content-Type: text/xml, SOAPAction: ""             │
│  Maneja SOAP Fault y HTTP errors                             │
│  Retorna texto del <loginCmsReturn>                          │
└──────────────────────────────────────────────────────────────┘
                  │
                  ▼
┌──────────────────────────────────────────────────────────────┐
│  parse_login_ticket_response(xml)                [client.py] │
│  Extrae de <loginTicketResponse>:                            │
│    credentials/token                                         │
│    credentials/sign                                          │
│    header/generationTime                                     │
│    header/expirationTime                                     │
└──────────────────────────────────────────────────────────────┘
                  │
                  ▼
┌──────────────────────────────────────────────────────────────┐
│  WsaaToken { token, sign, generation_time, expiration_time } │
└──────────────────────────────────────────────────────────────┘
```

### `tra.py` — Generación del TRA

```python
def build_tra(service: str, ttl_seconds: int = 2400) -> bytes:
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
```

**Detalles importantes:**
- `generationTime` se resta 60s para tolerar drift de reloj del cliente
- `uniqueId` es random 31-bit (range positivo de int signed) — debe ser único por TRA
- TTL default 2400s (40min) — AFIP acepta hasta 12h

### `signing.py` — CMS/PKCS7

```python
def sign_tra(tra: bytes, cert_path: Path, key_path: Path) -> str:
    cert = load_certificate(cert_path)
    key = load_private_key(key_path)

    signed_smime = (
        pkcs7.PKCS7SignatureBuilder()
        .set_data(tra)
        .add_signer(cert, key, hashes.SHA256())
        .sign(serialization.Encoding.SMIME, [pkcs7.PKCS7Options.Binary])
    )

    msg = email.message_from_string(signed_smime.decode("utf-8"))
    for part in msg.walk():
        filename = part.get_filename() or ""
        if filename.startswith("smime.p7"):
            return part.get_payload(decode=False).replace("\n", "").strip()
    raise RuntimeError("No se encontró la parte firmada smime.p7s")
```

**Por qué SMIME y no DER directo:**
`PKCS7SignatureBuilder.sign(Encoding.SMIME, [PKCS7Options.Binary])` produce un mensaje MIME multipart con la firma como adjunto `smime.p7s`. Es el formato que históricamente esperaba AFIP. WSAA acepta el payload base64 del `.p7s` sin los headers MIME.

Se usa `email.message_from_string` del stdlib para parsear el multipart sin agregar dependencias.

### `client.py` — SOAP/HTTP

```python
class WsaaEnvironment(StrEnum):
    HOMOLOGACION = "https://wsaahomo.afip.gov.ar/ws/services/LoginCms"
    PRODUCCION = "https://wsaa.afip.gov.ar/ws/services/LoginCms"

SOAP_ENVELOPE = """<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="..." xmlns:wsaa="...">
  <soapenv:Header/>
  <soapenv:Body>
    <wsaa:loginCms>
      <wsaa:in0>{cms}</wsaa:in0>
    </wsaa:loginCms>
  </soapenv:Body>
</soapenv:Envelope>"""

def call_login_cms(cms_b64: str, endpoint: str, timeout: float = 30.0) -> str:
    body = SOAP_ENVELOPE.format(cms=cms_b64)
    response = httpx.post(endpoint, content=body.encode("utf-8"),
                          headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": ""},
                          timeout=timeout)
    response.raise_for_status()

    root = etree.fromstring(response.content)
    fault = root.find(".//{soap}Fault", ns)
    if fault is not None:
        raise ValueError(f"WSAA SOAP Fault: {fault.findtext('faultstring')}")

    login_response = root.find(".//{*}loginCmsReturn")
    if login_response is None or login_response.text is None:
        raise ValueError("Respuesta WSAA sin loginCmsReturn")
    return login_response.text
```

**Excepciones que puede lanzar:**
- `httpx.ConnectError`, `httpx.TimeoutException` → red
- `httpx.HTTPStatusError` → 4xx/5xx
- `ValueError` con prefijo "WSAA SOAP Fault" → fault de auth

### `login.py` — Orquestación

```python
def validate_wsaa_login(
    cert_path: Path,
    key_path: Path,
    service: str = "wsfe",
    environment: WsaaEnvironment = WsaaEnvironment.HOMOLOGACION,
) -> SetupCheckResult:
```

Mapeo de errores → `ArcaErrorCause`:

| Excepción | Cause |
|---|---|
| `CertificateLoadError` | `CERT_INVALID` |
| `PrivateKeyLoadError` | `KEY_INVALID` |
| `httpx.ConnectError`, `TimeoutException` | `WSAA_UNREACHABLE` |
| `httpx.HTTPStatusError` | `WSAA_AUTH_FAILED` |
| `ValueError` con "alias" o "computador no autorizado" | `SERVICE_UNAUTHORIZED` |
| `ValueError` genérico | `WSAA_AUTH_FAILED` |

`validate_service_authorization` es un wrapper que valida que `service` no esté vacío y delega al login.

### `services.py` — Catálogo `ArcaService`

```python
class ArcaService(StrEnum):
    WSFE = "wsfe"                          # Factura Electrónica
    WSFEX = "wsfex"                        # Factura de Exportación
    WSMTXCA = "wsmtxca"                    # Factura con detalle
    WS_SR_PADRON_A4 = "ws_sr_padron_a4"    # Padrón nivel 4
    WS_SR_PADRON_A5 = "ws_sr_padron_a5"
    WS_SR_PADRON_A13 = "ws_sr_padron_a13"
    WSBFEV1 = "wsbfev1"                    # Bono Fiscal
    WSCTG = "wsctg"                        # Carta de Porte
    WSLPG = "wslpg"                        # Liquidación Granos
    WSREMCARNE = "wsremcarne"              # Remito Cárnico
    WSREMHARINA = "wsremharina"            # Remito Harinero
    WSREMAZUCAR = "wsremazucar"            # Remito Azúcar
    WSCPE = "wscpe"                        # Carta de Porte Electrónica
```

**No es whitelist rígida:** la función acepta cualquier string. El enum es solo para autocomplete y documentación de los servicios más comunes.

---

## Tools MCP

### `mcp/certificates.py` — 4 tools

```python
@server.tool
def validate_certificate(cert_path: str) -> CertificateValidationResult

@server.tool
def validate_private_key(key_path: str) -> CertificateValidationResult

@server.tool
def validate_cert_key_match(cert_path: str, key_path: str) -> CertificateValidationResult

@server.tool
def inspect_certificate(cert_path: str) -> CertificateInspection | CertificateValidationResult
```

Reciben paths como `str`, los convierten a `Path` y delegan a la capa de dominio.

### `mcp/setup.py` — 3 tools

```python
@server.tool
def validate_wsaa_login(cert_path: str, key_path: str, service: str = "wsfe") -> SetupCheckResult

@server.tool
def validate_service_authorization(cert_path: str, key_path: str, service: str) -> SetupCheckResult

@server.tool
def setup_doctor(cert_path: str, key_path: str, service: str = "wsfe") -> SetupDoctorReport
```

Todas hard-codean `WsaaEnvironment.HOMOLOGACION` en esta versión. v5 expondrá producción con confirmación adicional.

### Registro en el server

```python
# server.py
mcp = fastmcp.FastMCP(name="arca-mcp", instructions="...")
mcp.mount(certificates.server)
mcp.mount(setup.server)

def main():
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport == "http":
        mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)
    else:
        mcp.run(transport="stdio")
```

Soporta dos transportes:
- **stdio** — para integración con clientes MCP locales (Claude Desktop, IDE plugins)
- **streamable-http** — para Docker / acceso remoto (puerto 8000)

Las 7 tools se registran como funciones top-level (no namespaced) porque FastMCP merge los mounts en el namespace raíz por default.

---

## Setup Doctor — orquestador

### `wsaa/doctor.py`

```python
class NamedCheck(BaseModel):
    name: str
    ok: bool
    cause: ArcaErrorCause | None = None
    message: str | None = None
    skipped: bool = False

class SetupDoctorReport(BaseModel):
    checks: list[NamedCheck]
    all_ok: bool
    failed_check: str | None = None
```

### Algoritmo: short-circuit graceful

Ejecuta 5 checks en orden:

1. `private_key`
2. `certificate`
3. `cert_key_match`
4. `wsaa_login`
5. `service_authorization`

Al primer fallo, se marca `failed_check` y **todos los checks downstream se agregan con `skipped=True`** para que el reporte siempre tenga los 5 ítems. Esto permite al agente saber exactamente qué se evaluó y qué no.

Ejemplo de output con falla en check 3:

```json
{
  "all_ok": false,
  "failed_check": "cert_key_match",
  "checks": [
    {"name": "private_key", "ok": true},
    {"name": "certificate", "ok": true},
    {"name": "cert_key_match", "ok": false, "cause": "CERT_KEY_MISMATCH",
     "message": "El certificado no corresponde a la private key"},
    {"name": "wsaa_login", "ok": false, "skipped": true,
     "message": "saltado por cert/key mismatch"},
    {"name": "service_authorization", "ok": false, "skipped": true,
     "message": "saltado por cert/key mismatch"}
  ]
}
```

---

## Testing

### Suite: 64 tests

| Archivo | Tests | Cubre |
|---|---|---|
| `test_certificates_loader.py` | 6 | I/O PEM (file not found, invalid, valid x509/RSA) |
| `test_certificates_validator.py` | 8 | Validez, expiración, not-yet-valid, key inválida |
| `test_cert_key_match.py` | 4 | Match, mismatch, cert inválido, key inválida |
| `test_inspect_certificate.py` | 7 | CN, org, serial, fechas ISO, is_self_signed |
| `test_errors.py` | 7 | `wrap_error()` para todos los tipos de excepción |
| `test_wsaa_tra.py` | 6 | XML válido, service, uniqueId único, gen<exp |
| `test_wsaa_signing.py` | 4 | Output base64, distintos TRAs, cert/key inválidos |
| `test_wsaa_client.py` | 3 | Parseo de respuesta WSAA (válida, sin creds, incompleta) |
| `test_wsaa_login.py` | 7 | Login OK + 6 modos de falla |
| `test_wsaa_service_authorization.py` | 6 | Autorizado, alias fault, vacío, enum |
| `test_setup_doctor.py` | 6 | All OK + falla en cada nivel + skipped propagado |

### Fixture global (`conftest.py`)

```python
@pytest.fixture
def cert_key_pair(tmp_path) -> tuple[Path, Path]:
    """Genera cert autofirmado + private key RSA reales en tmp_path."""
```

Todos los tests que necesitan cert/key reales usan este fixture en lugar de tener cert/key mockeados.

### Mocking de WSAA

Los tests de login usan `pytest-mock` para mockear `call_login_cms`:

```python
def test_login_success(cert_key_pair, mocker):
    cert_path, key_path = cert_key_pair
    mocker.patch("arca_mcp.wsaa.login.call_login_cms", return_value=SUCCESS_RESPONSE)
    result = validate_wsaa_login(cert_path, key_path)
    assert result.ok is True
```

Esto permite testear toda la lógica (incluyendo CMS signing real con `cryptography`) sin pegarle a homologación.

### Tests E2E manual

Ejemplo de test end-to-end vía cliente FastMCP (no automatizado, solo verificación durante desarrollo):

```python
async with Client(mcp) as c:
    r = await c.call_tool("setup_doctor", {"cert_path": "...", "key_path": "..."})
    print(r.data.failed_check)
    for ch in r.data.checks:
        print(f"  {ch.name} → {ch.ok}")
```

---

## Infraestructura y Docker

### `Dockerfile` (multi-stage)

```dockerfile
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
COPY pyproject.toml .
RUN uv sync --no-install-project --no-dev
COPY src/ src/
RUN uv sync --no-dev

FROM python:3.12-slim-bookworm
WORKDIR /app
COPY --from=builder /app/.venv .venv
COPY --from=builder /app/src src/
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"
VOLUME ["/certs"]
EXPOSE 8000
CMD ["python", "-m", "arca_mcp.server"]
```

**Decisiones:**
- Builder con `uv` para resolución rápida de dependencias
- Imagen final mínima (`python:3.12-slim`) sin `uv` ni libs de build
- `VOLUME ["/certs"]` — los certificados se montan desde el host, nunca se copian a la imagen
- `EXPOSE 8000` para transporte HTTP

### `docker-compose.yml`

```yaml
services:
  arca-mcp:
    build: .
    ports: ["8000:8000"]
    env_file: [.env]
    volumes:
      - ${CERTS_DIR:-./certs}:/certs:ro
    restart: unless-stopped
```

`:ro` (read-only) es defensa en profundidad: incluso si el proceso es comprometido no puede modificar los certificados.

### Variables de entorno

| Variable | Default | Uso |
|---|---|---|
| `MCP_TRANSPORT` | `stdio` | `http` cuando corre en Docker |
| `ARCA_ENVIRONMENT` | `homologacion` | `produccion` deshabilitado en v0 |
| `ARCA_CERT_PATH` | `None` | Ruta al cert (en config global) |
| `ARCA_KEY_PATH` | `None` | Ruta a la key |
| `ARCA_CUIT` | `None` | CUIT del emisor |

En v0 los paths se pasan por tool argument, no por env (más flexible para multi-tenancy futuro).

---

## Decisiones técnicas clave

### 1. No usar `pyafipws`

**Problema:** `pyafipws` (la librería de referencia para integraciones AFIP en Python) depende de `pysimplesoap`, que importa `distutils.version`. `distutils` fue removido del stdlib en Python 3.12. Toda la cadena `pyafipws.wsaa` no se puede importar.

**Decisión:** Implementar WSAA desde cero. ~135 líneas total (`tra.py` + `signing.py` + `client.py` + `login.py`). El CMS signing usa `cryptography.pkcs7` que es la misma API que `pyafipws.sign_tra_new` usa internamente.

**Trade-off aceptado:** más código nuestro, pero sin dependencias muertas y compatible con Python 3.12+.

### 2. FastMCP `mount` en lugar de un solo server

Separar las tools en `mcp/certificates.py` y `mcp/setup.py` permite:
- Tests más enfocados por dominio
- Posibilidad futura de mount con namespaces (`certificates_validate_certificate`, etc.) si crece

### 3. Errores como datos, no como excepciones cruzando la frontera MCP

Las tools MCP **nunca** lanzan excepciones al cliente. Siempre devuelven un Pydantic con `valid`/`ok` + `cause` + `message`. El LLM puede branchear sobre `cause` (StrEnum) en lugar de parsear strings.

Las excepciones existen internamente (`CertificateLoadError`, `httpx.ConnectError`) pero se atrapan en el borde y se mapean a `ArcaErrorCause`.

### 4. Short-circuit con skipped en setup_doctor

Alternativa descartada: cortar y devolver solo los checks que se corrieron. Eso obligaba al cliente a deducir qué falta.

Elegido: siempre 5 checks, los downstream marcados `skipped=True`. El cliente sabe exactamente qué se evaluó y qué no.

### 5. Separación `errors.py` ↔ `error_mapping.py`

`errors.py` tiene solo tipos (StrEnum + Pydantic). `error_mapping.py` tiene la función `wrap_error()` que importa de toda la capa de dominio.

Esto evita el circular import: `certificates.models` necesita `ArcaErrorCause`, pero `wrap_error` necesita las excepciones de `certificates.errors`. Si todo viviera junto, no se podía cargar.

### 6. `CertificateInspection | CertificateValidationResult` como return type

Decisión: usar union type explícito en `inspect_certificate`. Alternativa: hacer que tire excepción. Trade-off: el union refleja mejor que el cliente debe distinguir éxito de error.

### 7. `tests/conftest.py` con cert_key_pair real

No mockear `cryptography`. Generar certs/keys reales con `rsa.generate_private_key` en `tmp_path`. Más lento (~1s por suite) pero testea el path real.

### 8. Sin TaskCreate / TODO list local

Toda la gestión de tareas vive en meridian (`mcp__meridian__*`). El proyecto no tiene `tasks.md` ni similares locales.

---

## Métricas

| Métrica | Valor |
|---|---|
| Tools MCP funcionando | 7 |
| Módulos de dominio | 2 implementados (certificates, wsaa) + 5 reservados |
| Tests | 64 (todos passing) |
| Tiempo total del suite | ~3s |
| LOC de implementación | ~700 (sin tests) |
| LOC de tests | ~800 |
| Dependencias runtime | 7 (fastmcp, cryptography, lxml, pydantic, pydantic-settings, playwright, httpx) |
| Dependencias dev | 3 (pytest, pytest-asyncio, pytest-mock) |
| Tamaño imagen Docker | ~150MB (slim + deps) |

### Tools y sus checks correspondientes

| Tool MCP | Llama a | Mapea errores a |
|---|---|---|
| `validate_certificate` | `certificates.validate_certificate` | CERT_INVALID, CERT_EXPIRED, CERT_NOT_YET_VALID |
| `validate_private_key` | `certificates.validate_private_key` | KEY_INVALID |
| `validate_cert_key_match` | `certificates.validate_cert_key_match` | CERT_KEY_MISMATCH, CERT_INVALID, KEY_INVALID |
| `inspect_certificate` | `certificates.inspect_certificate` | CERT_INVALID |
| `validate_wsaa_login` | `wsaa.validate_wsaa_login` | + WSAA_UNREACHABLE, WSAA_AUTH_FAILED, SERVICE_UNAUTHORIZED |
| `validate_service_authorization` | `wsaa.validate_service_authorization` | + SERVICE_UNAUTHORIZED |
| `setup_doctor` | `wsaa.run_setup_doctor` | (todos los anteriores con `skipped` propagado) |

---

## Próximos pasos sugeridos

- **v1 — Cache de tokens WSAA:** persistir `WsaaToken` con TTL, refresh automático
- **v2 — Primera consulta real:** `get_taxpayer_details` (padrón A4/A5)
- **v3 — Emisión:** flow `draft → validate → confirm` para WSFEv1
- **v4 — Playwright:** automatización del registro de certificados en WSASS

Cada fase se apoya en la capa de v0:
- WSAA login → cache (v1) → uso para llamar WSFE/padrón (v2/v3)
- Errores estructurados → mismo pattern en todos los servicios
- Setup doctor → diagnóstico previo a cualquier operación nueva
