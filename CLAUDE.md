meridian: arca-mcp

# MCP ARCA — CLAUDE.md

## Stack

- Python 3.12+
- FastMCP (sobre el SDK oficial MCP de Python)
- `cryptography` — X509, CMS signing
- `zeep` — cliente SOAP para WSFE
- `lxml` — procesamiento XML
- `pydantic` — validación de inputs/outputs
- `playwright` — automatización del portal ARCA
- `pytest` — testing

## Arquitectura

```
src/
  mcp/           # definición de tools MCP (FastMCP)
  arca/          # lógica de negocio fiscal
  wsaa/          # autenticación WSAA (token + sign)
  certificates/  # manejo X509, CSR, CMS signing
  policy/        # reglas de validación y seguridad
  validation/    # validaciones fiscales (CUIT, IVA, comprobantes)
  audit/         # logging de operaciones
  playwright/    # automatización portal ARCA
```

## Principios de Diseño

### Determinismo
Cada tool recibe inputs estructurados y retorna outputs estructurados. Sin inferencias ocultas, sin heurísticas fiscales invisibles.

### Human in the Loop
Acciones irreversibles (emisión de comprobantes) siguen el flujo:
```
create_voucher_draft → validate_voucher_draft → confirm_voucher_creation
```
Nunca emitir directamente sin confirmación explícita del usuario.

### Seguridad
- La private key nunca se expone al LLM ni aparece en respuestas MCP
- El MCP opera localmente: firma CMS, login WSAA, manejo de credenciales
- Homologación y producción son ambientes estrictamente separados

### Idempotencia
Toda operación irreversible recibe un `idempotency_key` para evitar doble facturación y reintentos accidentales.

## Reglas de Código

- No usar singletons a menos que sea estrictamente necesario
- Validar inputs con Pydantic en la capa MCP antes de pasar a capas internas
- Errores opacos de ARCA deben transformarse en estructuras `{"cause": "...", "message": "..."}` legibles
- No mezclar lógica de homologación y producción en el mismo módulo

## Ambientes

- **homologación** — certificados "Computadores Test", sin impacto fiscal real
- **producción** — certificados productivos, operaciones irreversibles

El ambiente debe ser siempre explícito en configuración; nunca inferido.

## Roadmap

| Versión | Fase | Estado | Entrega principal |
|---|---|---|---|
| v0.1 | Setup Doctor | ✅ Released | Diagnóstico técnico de certificados + WSAA |
| v0.2 | Lookup Layer | ✅ Released | Consultas deterministas (padrón, catálogos, validaciones) |
| v0.3 | WSAA Infra Robusta | ⏳ | Caché de token, retry, observabilidad |
| v0.4 | Draft-Based Invoicing | ⏳ | Emisión segura con `draft → validate → confirm` |
| v0.5 | Event Layer | ⏳ | Comprobantes entrantes, webhooks |
| v1.0 | Producción + Playwright | ⏳ | Producción habilitada + automatización del portal ARCA |

**Fuente de verdad:** `docs/ROADMAP.md` (scope, criterios de aceptación, dependencias por fase).
**Diseño estratégico:** meridian → `arca-mcp/research/verticales-y-roadmap-estrategico.md`.

**Wedge estratégico:** "hacer usable ARCA para developers y agentes", no "AI para impuestos". Fuera de scope inicial: WSMTXCA, Factura MiPyME, Exportación, Agro, SIRE.
