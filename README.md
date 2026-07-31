# arca-mcp

[![CI](https://github.com/macward/arca-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/macward/arca-mcp/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

MCP server para operaciones fiscales con ARCA/AFIP. Expone herramientas deterministas para consulta de catálogos, validación de contribuyentes y emisión de comprobantes mediante un flujo Human-in-the-Loop.

> **Estado:** v0.6.0 — solo homologación. Producción habilitada en v1.0.

---

## Requisitos

- Python 3.12+
- Certificado digital ARCA (`.crt`) y clave privada (`.key`)
- CUIT del emisor habilitado en ARCA para el servicio `wsfe`

---

## Instalación

```bash
git clone https://github.com/macward/arca-mcp
cd arca-mcp
uv sync
```

---

## Configuración

El servidor se configura con variables de entorno (o un archivo `.env` en la raíz):

| Variable | Requerida | Descripción |
|---|---|---|
| `ARCA_CERT_PATH` | Sí | Path absoluto al certificado `.crt` |
| `ARCA_KEY_PATH` | Sí | Path absoluto a la clave privada `.key` |
| `ARCA_CUIT` | Sí | CUIT del emisor (11 dígitos, sin guiones) |
| `ARCA_ENVIRONMENT` | No | `homologacion` (default) o `produccion` |
| `ARCA_AUDIT_LOG_PATH` | No | Path del audit log de emisiones (default: `/tmp/arca_audit.jsonl`) |
| `ARCA_TOKEN_CACHE_DIR` | No | Directorio de caché de tokens WSAA (default: `~/.arca-mcp/tokens/`) |

Ejemplo `.env`:

```env
ARCA_CERT_PATH=/certs/homo.crt
ARCA_KEY_PATH=/certs/homo.key
ARCA_CUIT=20123456789
ARCA_ENVIRONMENT=homologacion
```

---

## Uso

### stdio (Claude Desktop / MCP CLI)

```bash
arca-mcp
```

Configuración en Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "arca": {
      "command": "uv",
      "args": ["run", "--project", "/path/to/arca-mcp", "arca-mcp"],
      "env": {
        "ARCA_CERT_PATH": "/certs/homo.crt",
        "ARCA_KEY_PATH": "/certs/homo.key",
        "ARCA_CUIT": "20123456789"
      }
    }
  }
}
```

### HTTP (streamable-http)

```bash
MCP_TRANSPORT=http arca-mcp
```

### Docker

```bash
cp .env.example .env  # completar con tus valores
docker compose up -d
```

Los certificados se montan como volumen desde `CERTS_DIR` (default: `./certs`). Nunca se copian dentro de la imagen.

---

## Herramientas

### Setup y diagnóstico

| Tool | Descripción |
|---|---|
| `setup_doctor` | Diagnóstico completo: cert, key, WSAA login, autorización de servicio |
| `validate_wsaa_login` | Verifica login WSAA y retorna token vigente |
| `validate_service_authorization` | Verifica que el certificado esté autorizado para un servicio ARCA |

### Certificados

| Tool | Descripción |
|---|---|
| `validate_certificate` | Valida estructura y vigencia del certificado `.crt` |
| `validate_private_key` | Valida que la clave privada sea parseable |
| `validate_cert_key_match` | Verifica que cert y key correspondan al mismo par |
| `inspect_certificate` | Retorna subject, issuer, validez y CUIT del certificado |

### Catálogos y padrón

| Tool | Descripción |
|---|---|
| `get_voucher_types` | Tipos de comprobante disponibles en WSFEv1 |
| `get_document_types` | Tipos de documento soportados |
| `get_tax_types` | Tipos de tributo |
| `get_aliquot_types` | Alícuotas de IVA |
| `get_currency_types` | Monedas disponibles |
| `get_taxpayer_details` | Datos del contribuyente desde padrón A4 |
| `validate_taxpayer_status` | Estado fiscal del contribuyente |
| `validate_invoice_type` | Valida tipo de comprobante sin red |
| `validate_vat_condition` | Valida condición IVA sin red |
| `validate_currency` | Valida código de moneda sin red |

### Emisión de comprobantes

La emisión sigue un flujo de tres pasos obligatorio. Ningún paso puede saltarse.

```
create_voucher_draft → validate_voucher_draft → confirm_voucher_creation
```

| Tool | Descripción |
|---|---|
| `create_voucher_draft` | Crea un borrador en estado `PENDING`. No genera ningún comprobante fiscal. |
| `validate_voucher_draft` | Valida el borrador contra reglas fiscales. Transiciona a `VALIDATED` si pasa, permanece `PENDING` con detalle de errores si no. |
| `confirm_voucher_creation` | Emite el comprobante a WSFEv1, obtiene el CAE y registra la operación. Requiere `idempotency_key`. |
| `get_last_voucher_number` | Último número de comprobante autorizado para un punto de venta y tipo. |
| `get_voucher_info` | Datos completos de un comprobante específico desde WSFEv1. |

#### Ejemplo de flujo completo

```
1. create_voucher_draft(
     cbte_tipo=6,           # Factura B
     punto_venta=1,
     fecha_cbte="20260519",
     cuit_receptor="27000000000",
     doc_tipo=80,           # CUIT
     imp_neto="1000.00",
     alicuota_id="5"        # 21%
   )
   → { draft_id: "uuid-...", status: "PENDING", imp_total: "1210.00" }

2. validate_voucher_draft(draft_id="uuid-...")
   → { is_valid: true, status: "VALIDATED", errors: [] }

3. confirm_voucher_creation(
     draft_id="uuid-...",
     idempotency_key="mi-key-unica-001"
   )
   → { cae: "12345678901234", cbte_nro: 42, cae_fch_vto: "20260529" }
```

#### Idempotencia

`confirm_voucher_creation` exige un `idempotency_key` único por operación. Reintentar con la misma key retorna el resultado original sin volver a emitir. Si una emisión está en curso, retorna `EMISSION_IN_PROGRESS`.

---

## Errores

Todas las herramientas retornan errores estructurados:

```json
{
  "error": {
    "cause": "WSAA_AUTH_FAILED",
    "message": "El certificado venció el 2026-01-01."
  }
}
```

Causas comunes:

| Causa | Descripción |
|---|---|
| `MISSING_CONFIG` | Variable de entorno requerida no configurada |
| `WSAA_AUTH_FAILED` | Login WSAA fallido (cert vencido, key incorrecta, etc.) |
| `DRAFT_NOT_FOUND` | `draft_id` no existe en el store |
| `DRAFT_NOT_VALIDATED` | Se intentó confirmar un draft sin validar |
| `DRAFT_INVALID_STATUS` | La operación requiere un estado distinto al actual |
| `EMISSION_IN_PROGRESS` | Otra confirmación con la misma `idempotency_key` está en curso |
| `WSFE_REJECTED` | WSFEv1 rechazó el comprobante (ver `observaciones`) |
| `UNSUPPORTED_ENVIRONMENT` | Operación no disponible en producción (v0.x) |
| `ARCA_SERVICE_ERROR` | Error SOAP o de red contra ARCA |

---

## Seguridad

- La clave privada nunca aparece en respuestas MCP ni en logs.
- Los tokens WSAA se persisten en `~/.arca-mcp/tokens/` con permisos `0600`.
- Homologación y producción son ambientes estrictamente separados en configuración.
- `fecae_solicitar` bloquea producción hasta v1.0.

---

## Desarrollo y tests

```bash
# Instalar dependencias de desarrollo
uv sync

# Ejecutar tests (excluye E2E que requieren credenciales reales)
pytest -m "not e2e"

# Tests E2E contra wsaahomo.afip.gov.ar
ARCA_TEST_CERT_PATH=/certs/homo.crt ARCA_TEST_KEY_PATH=/certs/homo.key pytest -m e2e
```

---

## Tutoriales

| # | Tema |
|---|---|
| 1 | [Setup inicial — instalación, certificados y setup_doctor](docs/tutorials/01-setup.md) |
| 2 | [Emitir una factura — flujo completo draft → validate → confirm](docs/tutorials/02-emitir-factura.md) |
| 3 | [Consultas al padrón — datos y estado fiscal del contribuyente](docs/tutorials/03-padron.md) |
| 4 | [Integración con Claude Desktop — configuración paso a paso](docs/tutorials/04-claude-desktop.md) |

---

## Changelog

Ver [CHANGELOG.md](CHANGELOG.md).
