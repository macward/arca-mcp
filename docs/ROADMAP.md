# MCP ARCA — Roadmap de Releases

> Fuente de verdad del roadmap del proyecto. Cualquier mención a fases o versiones en otros docs debe apuntar acá.

## Convenciones

**Versionado:** [SemVer 2.0.0](https://semver.org/spec/v2.0.0.html).

- `0.x.0` indica fase pre-estable. Cada minor agrega una vertical completa.
- `1.0.0` marca el primer release production-ready: producción ARCA habilitada con todas las salvaguardas.
- `0.x.y` (patch) para fixes que no agregan scope.
- Breaking changes pre-1.0 son aceptables; deben quedar registrados en `CHANGELOG.md`.

**Wedge estratégico:** "hacer usable ARCA para developers y agentes". Las fases priorizan reducir fricción y validar antes que emitir.

**Criterios de aceptación:** cada fase tiene una lista cerrada. Se cierra cuando todos están en ✅. Si un criterio se reabre, la versión queda en patch (`0.x.y+1`) hasta resolver.

---

## Vista general

| Versión | Fase | Estado | Entrega principal |
|---|---|---|---|
| **v0.1** | Setup Doctor | ✅ Released | Diagnóstico técnico de certificados + WSAA |
| **v0.2** | Lookup Layer | 🚧 En diseño | Consultas deterministas a ARCA (padrón, catálogos, validaciones) |
| **v0.3** | WSAA Infra Robusta | ⏳ Planificado | Caché de token, retry, observabilidad |
| **v0.4** | Draft-Based Invoicing | ⏳ Planificado | Emisión segura con flow `draft → validate → confirm` |
| **v0.5** | Event Layer | ⏳ Planificado | Comprobantes entrantes, webhooks, detección de eventos |
| **v1.0** | Producción + Playwright | ⏳ Planificado | Producción habilitada + automatización del portal ARCA |

---

## v0.1 — Setup Doctor

**Estado:** ✅ Released
**Objetivo:** Resolver el onboarding técnico. Convertir errores opacos de ARCA en diagnósticos accionables.

### Scope

- Validación de certificados X.509 (vigencia, integridad, parsing)
- Validación de private keys RSA
- Verificación de match cert ↔ key
- Inspección de metadata del certificado
- Login WSAA contra homologación
- Verificación de autorización a servicios ARCA
- Orquestador `setup_doctor` con short-circuit y `skipped` propagado
- Capa de errores estructurados (`ArcaErrorCause` StrEnum)

### Out of scope

- Producción
- Caché de token WSAA
- Tools de consulta fiscal
- Generación de CSR / Playwright

### Criterios de aceptación

- [x] 7 tools MCP expuestas: `validate_certificate`, `validate_private_key`, `validate_cert_key_match`, `inspect_certificate`, `validate_wsaa_login`, `validate_service_authorization`, `setup_doctor`
- [x] Suite de tests ≥ 70 unit tests, todos en verde
- [x] Errores normalizados a `ArcaErrorCause` (catálogo cerrado, JSON-serializable)
- [x] Build Docker (multi-stage) + `docker-compose.yml` con `:ro` en `/certs`
- [x] Soporte transportes `stdio` y `streamable-http`
- [x] Documentación técnica completa (`docs/v0_documento_tecnico.md`)
- [x] E2E test opt-in contra `wsaahomo.afip.gov.ar` (cerrado en `v0.1.2`, 2026-05-18 — verificado contra cert real de homologación)

> v0.1 cerrada formalmente en `v0.1.2`. Próximo movimiento: v0.2 (Lookup Layer).

---

## v0.2 — Lookup Layer

**Estado:** 🚧 En diseño
**Objetivo:** Convertir ARCA en una API moderna y consultable. Cero operaciones irreversibles — es el wedge de bajo riesgo para validar que el modelo MCP funciona end-to-end.

### Scope

**Padrón:**
- `get_taxpayer_details(cuit)` → datos completos del contribuyente (padrón A4/A5)
- `validate_taxpayer_status(cuit)` → estado activo / cancelado / etc.
- `get_cuit_from_dni(dni)` (si el padrón lo permite)

**Catálogos (servicios `WSFEv1` paramétricos):**
- `get_voucher_types()` → tipos de comprobantes
- `get_document_types()` → tipos de documento (DNI, CUIT, CUIL, ...)
- `get_tax_types()` → tipos de tributos
- `get_aliquot_types()` → alícuotas de IVA
- `get_currency_types()` → monedas y cotizaciones

**Validaciones derivadas (puras, sin red):**
- `validate_invoice_type(...)`
- `validate_vat_condition(...)`
- `validate_currency(...)`

### Out of scope

- Caché persistente del token WSAA (un re-login por sesión está bien para Lookup)
- Tools de emisión (`create_voucher_draft`, etc.)
- Webhooks / eventos
- Producción

### Criterios de aceptación

- [ ] **Decisión de configuración resuelta:** modelo per-call vs por-servidor vs híbrido para `environment` / `cert_path` / `key_path`. Brief en `docs/` o `plans/` con la decisión. *(task meridian `6eff2b81-...`)*
- [ ] Mínimo 5 tools de padrón + catálogos + 3 validaciones, todas expuestas como tools MCP
- [ ] Cada tool retorna Pydantic estructurado con cause/message ante error
- [ ] Cliente SOAP/REST para `ws_sr_padron_a4` y `wsfev1` (paramétricas) implementado sin `pyafipws`
- [ ] Caché en memoria del token WSAA durante la vida del proceso (no persistente)
- [ ] Suite de tests con cobertura unit ≥ v0.1
- [ ] **E2E test opt-in** contra padrón homologación, con cert/key reales (skip si no hay)
- [ ] Documentación: actualizar `v0_documento_tecnico.md` o crear `v0_2_documento_tecnico.md`

### Dependencias

- Cierre del criterio E2E de v0.1 (`v0.1.1`)
- Decisión de configuración (task meridian abierto)

---

## v0.3 — WSAA Infra Robusta

**Estado:** ⏳ Planificado
**Objetivo:** Endurecer WSAA para uso intensivo. Hasta v0.2 alcanza con re-login por sesión; v0.3 prepara la base para los volúmenes de v0.4–v0.5.

### Scope

- **Caché persistente del token WSAA** con TTL ≤ 12h (límite ARCA), refresh automático cuando faltan <N minutos
- **Política de retry explícita** con backoff exponencial para errores transitorios (`ConnectError`, `TimeoutException`)
- **Logs estructurados** de cada call WSAA (CUIT, servicio, latencia, resultado) — formato JSON
- **Métricas:** duración por call, success rate, número de refreshes de token
- **Multi-CUIT:** soporte para múltiples certificados activos simultáneamente (segregados por CUIT en el caché)
- **Reentrancia:** el módulo WSAA es seguro para usar desde múltiples sesiones concurrentes

### Out of scope

- Emisión de comprobantes
- Tracing distribuido (OpenTelemetry) — postpone a post-v1.0
- Métricas exportadas a Prometheus/Grafana — postpone

### Criterios de aceptación

- [ ] Token persistido en filesystem local (`~/.arca-mcp/tokens/`) o backend configurable, con permisos `0600`
- [ ] Refresh automático cuando faltan <10 min de TTL
- [ ] Retry configurable (default 2 intentos) con backoff (`100ms → 500ms`)
- [ ] Cada call WSAA emite un log JSON con: `ts`, `cuit`, `service`, `latency_ms`, `result` (`ok` | `cached` | `retried` | `failed`)
- [ ] Test de concurrencia: 10 sesiones simultáneas comparten el mismo token sin race condition
- [ ] Test de expiración: simular reloj del sistema y confirmar refresh
- [ ] Documento de operaciones: cómo limpiar el caché, cómo rotar certificados sin downtime

### Dependencias

- v0.2 completa (necesitamos uso real de WSAA para dimensionar)

---

## v0.4 — Draft-Based Invoicing

**Estado:** ⏳ Planificado
**Objetivo:** Habilitar emisión segura de comprobantes en homologación. Primera fase con operaciones potencialmente irreversibles, gestionadas por Human-in-the-Loop estricto.

### Scope

**Flow obligatorio (no hay shortcut):**
1. `create_voucher_draft(...)` → retorna draft inmutable + `draft_id`
2. `validate_voucher_draft(draft_id)` → corrige errores, completa campos derivados (CAE no incluido)
3. `confirm_voucher_creation(draft_id, idempotency_key)` → única tool que realmente emite

**Tools complementarias:**
- `get_last_voucher(point_of_sale, voucher_type)` — para numeración
- `get_voucher_info(cae, voucher_number)` — consulta posterior
- `generate_invoice_pdf(voucher_id)` — PDF con QR
- `generate_qr(voucher_data)` — QR de validación AFIP

**Infraestructura:**
- Módulo `audit/` activado: cada `confirm_voucher_creation` deja registro inmutable
- Módulo `policy/` activado: validación de reglas fiscales antes de confirmar
- `idempotency_key` obligatorio en confirm (rechaza duplicados)

### Out of scope

- Producción (solo homologación en v0.4)
- WSMTXCA, WSFEX, exportación, MiPyME (verticales enterprise diferidas a post-v1.0)
- Notas de crédito / débito automáticas (sí manuales)

### Criterios de aceptación

- [ ] Las 3 tools del flow draft → validate → confirm implementadas
- [ ] Imposible emitir sin `confirm_voucher_creation` (no hay backdoor)
- [ ] `idempotency_key` rechaza el segundo intento con la misma key (idempotente)
- [ ] Cada confirm genera audit log inmutable (append-only) con CUIT, draft_id, CAE, timestamp
- [ ] PDF generado contiene QR validable en el portal ARCA
- [ ] Test E2E contra `wsfev1` homologación: emisión completa + verificación posterior con `get_voucher_info`
- [ ] Test de idempotencia: re-confirm con misma key no duplica
- [ ] Documentación de los modelos fiscales soportados (Factura A/B/C, nota de crédito, nota de débito)

### Dependencias

- v0.3 (caché de token necesario para volumen de calls)

---

## v0.5 — Event Layer

**Estado:** ⏳ Planificado
**Objetivo:** Pasar de request/response a event-driven. Convertir ARCA en infraestructura observable.

### Scope

**Tools de consulta de entrantes:**
- `mis_comprobantes(date_range)` — comprobantes recibidos
- `watch_incoming_invoices()` — handle para polling
- `supplier_invoice_detection(cuit)` — detecta facturas de un proveedor

**Sistema de eventos:**
- Tipos: `invoice_received`, `invoice_approved`, `invoice_rejected`, `cae_expiring`, `certificate_expiring`
- Modo polling (default): cada N minutos consulta ARCA, dispara eventos
- Modo webhook (opcional): expone endpoint HTTP donde el cliente puede recibir push

**Configuración:**
- Suscripciones por evento + filtro
- Deduplicación: el mismo evento no se dispara dos veces

### Out of scope

- Webhooks salientes a servicios externos (Slack, Discord, etc.) — postpone a post-v1.0
- Reglas complejas de routing — postpone

### Criterios de aceptación

- [ ] `mis_comprobantes` funcional contra el servicio AFIP correspondiente
- [ ] Polling configurable (intervalo, scope)
- [ ] Modo webhook con endpoint local + verificación de firma
- [ ] Deduplicación validada por test
- [ ] Evento `certificate_expiring` dispara cuando faltan ≤ 30 días
- [ ] Documentación de los tipos de evento y payload de cada uno

### Dependencias

- v0.4 (necesitamos saber cómo modelar comprobantes para los eventos)

---

## v1.0 — Producción + Playwright

**Estado:** ⏳ Planificado
**Objetivo:** Primer release production-ready. Habilita producción real con todas las salvaguardas y agrega Playwright para cerrar el loop de onboarding técnico.

### Scope

**Habilitación de producción:**
- `environment="produccion"` aceptado en todas las tools relevantes
- Confirmación adicional obligatoria para operaciones en producción (doble HITL)
- Separación de procesos: típicamente un proceso homo-mcp y un proceso prod-mcp con configuración disjoint
- Auditoría legal-grade: backup automático del audit log, integridad verificable

**Playwright (módulo `playwright/`):**
- `generate_csr(cuit, ...)` — genera CSR localmente
- `register_certificate_in_wsass(csr, credentials)` — automatiza el flujo en el portal ARCA
- `download_certificate_from_wsass()` — descarga el cert generado
- Modo headed para auditoría visual + modo headless para producción

**Operaciones:**
- Documento de runbook para producción
- Procedimiento de rotación de certificados
- Disaster recovery del audit log

### Out of scope

- Verticales enterprise (WSMTXCA, MiPyME, Exportación, Agro, SIRE, Trazabilidad) — diferidas a v1.x o v2.x según demanda
- Multi-tenancy a nivel infraestructura (un MCP server por CUIT sigue siendo la recomendación)

### Criterios de aceptación

- [ ] Producción habilitable solo con flag explícito + confirmación de doble factor
- [ ] Auditoría legal-grade: audit log inmutable + checksum + backup automático
- [ ] Test E2E completo: onboarding via Playwright → setup_doctor → consulta padrón → emisión draft/confirm en homologación
- [ ] Playwright headless funciona en CI (sin display)
- [ ] Runbook operacional documentado (deploy, rollback, rotación de cert, recovery)
- [ ] Security review formal (third-party o auto-checklist OWASP) sin findings críticos
- [ ] Performance baseline: P99 < 2s para tools de lookup, < 5s para emisión
- [ ] `CHANGELOG.md` actualizado con migration guide desde v0.x

### Dependencias

- v0.5 completa
- Disponibilidad de un certificado productivo real para testing (riesgo: blockeable por trámite ARCA)

---

## Versionado de patches (`0.x.y`)

Patch releases entre fases para:

- Bugfixes que no agregan scope (ej: B1–B5 actuales)
- Mejoras de tests o documentación
- Dependencias actualizadas

Cada patch debe:
1. No introducir breaking changes (incluso pre-1.0)
2. Entrar a `CHANGELOG.md` bajo la versión correspondiente
3. Incrementar `__version__` en `src/arca_mcp/__init__.py`

Ejemplos:
- `0.1.1` — cerrar el E2E pendiente de v0.1
- `0.1.2` — fix B2-B5 (environment per-call, retry httpx, isoformat TRA, defensive exceptions)

---

## Política de cierre de versión

Una versión `0.x.0` se considera **released** cuando:

1. Todos los criterios de aceptación en ✅
2. Tests en verde en CI
3. `CHANGELOG.md` actualizado bajo la sección de esa versión
4. `__version__` bumpeado y tag git creado (`v0.x.0`)
5. Documento técnico actualizado o suplementado
6. Si aplica: brief de la próxima fase ya iniciado en `plans/`

Una versión queda **abierta** mientras haya criterios sin marcar. Si se descubre un criterio faltante después de tagear, abrir un patch (`0.x.y+1`) en vez de re-tagear.

---

## Cambios al roadmap

Cambios estratégicos al roadmap (reordenar fases, mover scope, agregar/quitar criterios) requieren:

1. Update de este documento en el mismo PR que el cambio
2. Update del resumen en `CLAUDE.md` si cambia la tabla de fases
3. Nota en `CHANGELOG.md` bajo `[Unreleased]` describiendo el cambio de roadmap
