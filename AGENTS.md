meridian: arca-mcp

# MCP ARCA — AGENTS.md

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

| Fase | Descripción |
|------|-------------|
| v0 | Setup Doctor — validación de certificados y WSAA |
| v1 | WSAA funcional en homologación |
| v2 | Tools MCP básicas (consultas, catálogos) |
| v3 | Draft → validate → confirm para comprobantes |
| v4 | Automatización Playwright del portal ARCA |
| v5 | Producción controlada |
