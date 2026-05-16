# MCP ARCA Determinista

## Visión General

MCP ARCA es un servidor MCP (Model Context Protocol) orientado a encapsular la complejidad técnica de ARCA/AFIP y exponer operaciones fiscales argentinas como tools deterministas, seguras y utilizables por agentes LLM.

El objetivo NO es crear un “chatbot fiscal”.

El objetivo es crear una capa de ejecución segura y estructurada sobre:

- certificados
- WSAA
- SOAP/XML
- WSFE
- padrón
- comprobantes
- validaciones fiscales

La idea central:

```txt
El agente propone.
El MCP valida.
ARCA confirma.
El usuario autoriza acciones irreversibles.
```

---

# Problema

La experiencia de integración actual con ARCA/AFIP presenta:

- SOAP legacy
- XML manual
- certificados X509
- autenticación WSAA
- separación homologación/producción
- mensajes de error opacos
- procesos manuales
- UX administrativa vieja
- documentación fragmentada

Ejemplos reales observados:

- errores ambiguos al asociar servicios
- necesidad de generar CSR manualmente
- validación manual de certificados
- configuración difícil para developers
- múltiples pasos administrativos invisibles

Esto genera una barrera enorme incluso para developers experimentados.

---

# Objetivo del Proyecto

Construir un servidor MCP determinista que:

1. abstraiga complejidad técnica de ARCA
2. automatice setup técnico donde sea posible
3. reduzca errores humanos
4. permita integración segura con agentes
5. evite ejecuciones irreversibles accidentales
6. transforme errores opacos en diagnósticos claros

---

# Filosofía de Diseño

## MCP determinista

El servidor NO toma decisiones fiscales autónomas.

El LLM:

- interpreta intención
- propone datos
- prepara borradores

El MCP:

- valida
- normaliza
- rechaza ambigüedad
- controla seguridad
- ejecuta

---

# Arquitectura Conceptual

```txt
Usuario
  ↓
LLM / Agente
  ↓
MCP ARCA
  ↓
Policy + Validation Layer
  ↓
WSAA / Certificados
  ↓
Servicios ARCA
  ↓
WSFE / Padrón / Comprobantes
```

---

# Principios Fundamentales

## 1. Human in the Loop

Acciones irreversibles requieren confirmación explícita.

Ejemplo:

```txt
create_voucher_draft
→ validate
→ confirm
→ execute
```

Nunca:

```txt
create_voucher()
```

emitiendo directamente sin confirmación.

---

## 2. Determinismo

Input:

```json
{
  "cuit": "203...",
  "amount": 100000
}
```

Resultado:

- validación clara
- error estructurado
- ejecución reproducible

No:

- inferencias ocultas
- heurísticas fiscales invisibles
- comportamiento impredecible

---

## 3. Seguridad

La private key nunca debe exponerse al LLM.

El MCP opera localmente:

- firma CMS
- validación de certificados
- login WSAA
- manejo de credenciales

---

## 4. Idempotencia

Toda operación irreversible debe usar:

```txt
idempotencyKey
```

para evitar:

- doble facturación
- reintentos accidentales
- loops de agentes

---

# Ambientes

## Homologación

Testing/sandbox.

Características:

- certificados “Computadores Test”
- endpoints separados
- sin impacto fiscal real
- CAEs de prueba

Objetivo inicial del proyecto.

---

## Producción

Entorno real.

Características:

- certificados productivos
- comprobantes reales
- operaciones irreversibles
- mayores requisitos administrativos

No se recomienda automatización completa inicial.

---

# Alcance Inicial (MVP)

## Fase 1 — Setup Doctor

Objetivo:

resolver el onboarding técnico.

### Tools

```txt
validate_private_key
validate_certificate
validate_cert_key_match
validate_wsaa_login
validate_service_authorization
inspect_certificate
```

### Valor

Transformar:

```txt
Error CMS inválido
```

en:

```json
{
  "cause": "CERT_KEY_MISMATCH",
  "message": "El certificado no corresponde a private.key"
}
```

---

# Fase 2 — Automatización Playwright

Objetivo:

automatizar onboarding ARCA.

## Capacidades

```txt
✔ generar CSR
✔ abrir WSASS
✔ pegar CSR
✔ descargar certificado
✔ validar resultado
✔ guardar archivos
```

## Limitaciones

No automatizar inicialmente:

```txt
✖ producción completa
✖ acciones administrativas críticas
✖ autorizaciones sensibles
```

---

# Fase 3 — WSAA

Objetivo:

obtener autenticación funcional.

Pipeline:

```txt
cert + key
→ CMS signing
→ WSAA
→ Token + Sign
→ acceso servicios
```

---

# Fase 4 — WSFE

Objetivo:

emisión segura de comprobantes.

## Flow

```txt
LLM
→ draft
→ validate
→ confirm
→ emit
```

---

# Tools MCP Propuestas

## Core Fiscal

```txt
get_last_voucher
get_voucher_info
get_taxpayer_details
get_sales_points
mis_comprobantes
```

---

## Drafts Seguros

```txt
create_voucher_draft
validate_voucher_draft
confirm_voucher_creation
```

---

## Setup / Certificados

```txt
setup_doctor
certificate_key_match
wsaa_login_test
service_access_test
```

---

## Metadata / Catálogos

```txt
get_voucher_types
get_document_types
get_tax_types
get_aliquot_types
get_currencies_types
```

---

# Diseño Interno

## Módulos

```txt
src/
  mcp/
  arca/
  wsaa/
  certificates/
  policy/
  validation/
  audit/
  playwright/
```

---

# Capa de Validación

El verdadero valor del sistema.

Validaciones:

```txt
✔ CUIT válido
✔ IVA válido
✔ tipo comprobante válido
✔ punto venta válido
✔ moneda válida
✔ certificado vigente
✔ WSAA accesible
✔ idempotency key válida
```

Rechazar automáticamente:

```txt
✖ inputs ambiguos
✖ montos inválidos
✖ ambientes mezclados
✖ certificados vencidos
✖ certificados incorrectos
```

---

# Playwright Integration

## Motivación

ARCA tiene:

- UX legacy
- flows manuales
- navegación compleja
- errores ambiguos

Playwright puede encapsular:

```txt
portal ARCA
→ interacción automática
→ flujo reproducible
```

---

# Posicionamiento

El producto NO es:

```txt
“AI para impuestos”
```

El producto es:

```txt
“hacer usable ARCA para developers y agentes”
```

---

# Riesgos

## Técnicos

- cambios de UI ARCA
- cambios SOAP
- flows inconsistentes
- errores silenciosos
- certificados vencidos

## Producto

- automatizar demasiado rápido
- permitir acciones irreversibles sin confirmación
- confiar demasiado en inferencias del LLM

---

# Reglas Críticas

## Nunca

```txt
✖ compartir private keys
✖ emitir automáticamente sin confirmación
✖ confiar en inferencias fiscales del LLM
✖ mezclar homologación y producción
```

---

# Roadmap Tentativo

## v0

Setup Doctor CLI.

## v1

WSAA funcional homologación.

## v2

MCP tools básicas.

## v3

Draft + validate + confirm.

## v4

Automatización Playwright.

## v5

Producción controlada.

---

# Conclusión

La parte más valiosa inicialmente no es emitir comprobantes.

Es encapsular:

- certificados
- WSAA
- onboarding
- errores
- homologación
- setup técnico

porque ahí existe una fricción real extremadamente alta.

El enfoque correcto es:

```txt
determinismo + validación + seguridad
```

no “agente autónomo fiscal”.

