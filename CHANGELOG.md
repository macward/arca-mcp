# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.6.1] - 2026-06-03

### Removed
- Módulos de caché WSAA superseded por `WsaaCache` (0.6.0): se eliminan `wsaa/token_cache.py` (`TokenCache`) y `wsaa/token_store.py`, que ya no eran importados por ningún módulo de `src/` (solo por tests). −620 LOC netas, sin cambios de API pública

### Changed
- Cobertura de `WsaaCache` consolidada en `tests/test_wsaa_cache.py`: la verificación de permisos 0600 del archivo de token ahora tiene un test **no-e2e** (antes solo existía en tests e2e que se skipean sin credenciales)

## [0.6.0] - 2026-05-28

### Added
- `WsaaCache` — clase unificada que reemplaza `token_store` + `TokenCache`; capa in-memory con `threading.Lock` y capa filesystem con `asyncio.Lock` por CUIT; escritura atómica con perms 0600 y refresh proactivo a <10min de expiración
- `IdempotencyStore` ahora persiste en SQLite (`~/.arca-mcp/idempotency.db`): métodos `set_pending` / `set_done` / `get` / `delete` / `cleanup_stale_pending`; startup recovery elimina entradas PENDING > 5min
- `DraftStore` ahora persiste en SQLite (`~/.arca-mcp/drafts.db`) con WAL mode y `threading.Lock`; los drafts sobreviven reinicios del proceso
- `AuditLog`: escritura atómica (`{path}.tmp` → rename + `fsync`), perms 0600, directorio `~/.arca-mcp/audit/`; entrada `PENDING_CAE` escrita antes de llamar a WSFE

### Fixed
- `validate_wsaa_login` retornaba `ok=True` cuando el token o firma obtenidos eran strings vacíos — ahora retorna `ok=False` con causa `WSAA_AUTH_FAILED`
- `_do_network_login` bloqueaba el event loop de asyncio — wrapeado con `asyncio.to_thread`
- `confirm_voucher_creation`: orden WAL corregido a `set_pending → PENDING_CAE → fecae_solicitar → set_done → CAE_CONFIRMED`; errores transitorios de WSFE eliminan la key para permitir retry
- `doc_tipo=99` (Consumidor Final): `cuit_receptor` acepta `"0"`, `DocNro=0` enviado a zeep, política fiscal omite validación de check-digit CUIT
- `doc_tipo=96` (DNI): `cuit_receptor` acepta 7-8 dígitos; política fiscal omite validación de CUIT
- `nroDocRec` en QR deriva correctamente del `tipoDocRec` (0 para CF, int para otros)
- Floats enteros serializan sin decimales en JSON del QR (`1000.0` → `1000`)
- `fecha_cbte` y `cae_fch_vto` rechazan fechas de calendario inválidas (ej. 30/02)
- Heurística `"codAut" in msg` reemplazada por inspección explícita de `ValidationError.errors()`
- Rama `ArcaError` en `build_qr_url` eliminada; tipo de retorno simplificado a `str`
- `Decimal` pasado directamente a zeep en `fecae_solicitar` — elimina conversiones a `float` con pérdida de precisión

## [0.5.0] - 2026-05-22

### Added
- `generate_invoice_pdf_tool` — genera un PDF de comprobante fiscal con formato estándar (encabezado, emisor/receptor, tabla de importes, CAE y QR embebido); retorna el PDF en base64 listo para descargar
- `generate_qr` — genera el código QR oficial ARCA (RG 4291/2018) de forma independiente; retorna la URL y el PNG en base64
- `ConfirmedVoucherInput` (`invoicing/pdf.py`) — modelo Pydantic que valida todos los campos del comprobante; auto-deriva `nro_doc_receptor` según `doc_tipo` (80→CUIT, 99→"0", otros→requerido explícito)
- `QRPayload` + `build_qr_url` + `generate_qr_png` (`invoicing/qr.py`) — construcción del payload QR según spec ARCA, codificación base64url y generación del PNG
- `ArcaErrorCause.INVALID_CAE` — nueva causa de error para CAEs inválidos
- Dependencias runtime: `qrcode[pil]>=7.4`, `reportlab>=4.5.1`
- Tests: 23 nuevos tests unitarios e integración (QR payload, QR PNG, PDF, tools MCP)

### Fixed
- `nro_doc_receptor` en el QR ahora refleja correctamente el tipo de documento del receptor: consumidores finales usan "0", personas físicas con DNI usan el número de DNI explícito; antes se usaba siempre el CUIT del receptor

## [0.4.0] - 2026-05-19

### Added
- `create_voucher_draft` — creates a draft invoice in PENDING state; no fiscal operation is performed until the flow is completed
- `validate_voucher_draft` — validates draft against fiscal policy rules; transitions to VALIDATED on success, stays PENDING on errors with violation details
- `confirm_voucher_creation` — submits validated draft to WSFEv1 (FECAESolicitar), retrieves CAE, marks draft CONFIRMED; idempotency_key prevents double emission
- `get_last_voucher_number` — queries last authorized voucher number for a given punto_venta and cbte_tipo
- `get_voucher_info` — retrieves full details of a specific voucher from WSFEv1
- `IdempotencyStore.set_if_absent` — atomic check-and-set prevents concurrent callers from both reaching `fecae_solicitar` with the same key

### Fixed
- Double-emission window in `confirm_voucher_creation`: sentinel is now written atomically at Step 2 (before any I/O) via `set_if_absent`; concurrent callers receive `EMISSION_IN_PROGRESS` error instead of raw sentinel dict
- `validate_voucher_draft` on non-PENDING drafts returned `INTERNAL_ERROR`; now returns structured `DRAFT_INVALID_STATUS` error
- `TokenCache._get_lock` check-then-set pattern replaced with `defaultdict(asyncio.Lock)` to eliminate theoretical race window
- `AuditLog.append` used synchronous `open()` inside asyncio lock, blocking the event loop; moved to `run_in_executor`
- Production guard in `fecae_solicitar` and `_wsdl_url` compared against string literal `"produccion"`; now compares against `Environment.PRODUCCION` enum
- `_ALICUOTA_RATES` duplicated between `invoicing/models.py` and `validation/catalogs.py`; `models.py` now imports `IVA_ALIQUOTS` from `catalogs.py`

## [0.3.0] - 2026-05-19

### Added
- **Token cache filesystem WSAA** (`wsaa/token_cache.py`) — persiste tokens entre sesiones en `~/.arca-mcp/tokens/{cuit}.json` con permisos `0600`. Refresh automático cuando faltan <10 min de TTL.
- **Logs estructurados por call WSAA** (`wsaa/wsaa_logger.py`) — emite JSON con `ts`, `cuit`, `service`, `latency_ms`, `result` (`ok` | `cached` | `retried` | `failed`) en cada operación WSAA.
- **Multi-CUIT en caché** — tokens segregados por CUIT; invalidar uno no afecta a los demás.
- `docs/operations-v0.3-wsaa-cache.md` — runbook de operaciones: limpiar caché, rotar certificados sin downtime.

### Changed
- **Filesystem cache activado en todas las tools MCP** (`mcp/lookup.py`) — `emitter_cuit` se pasa a `validate_wsaa_login`, activando la persistencia entre reinicios del servidor. Antes el `TokenCache` existía pero nunca se instanciaba desde las tools.
- Validación de `emitter_cuit` se ejecuta antes del login WSAA — evita un round-trip de red cuando el CUIT no está configurado.

### Tests
- Test de concurrencia: 10 sesiones simultáneas comparten el mismo token sin race condition (`test_10_concurrent_sessions_single_login`).
- Test de expiración: token expirado en disco fuerza re-login (`TestExpirationEndToEnd`).
- Test multi-CUIT: dos CUITs almacenados independientemente, invalidar uno no afecta al otro.
- 344 tests pasando, 3 skipped (E2E sin credenciales).

## [0.2.0] - 2026-05-18

### Added
- Token cache WSAA en memoria (`wsaa/token_store.py`) — evita re-login dentro de la sesión de proceso
- Cliente SOAP WSFEv1 paramétricas (`wsfe/client.py`) — 5 consultas de catálogo (tipos de comprobante, documento, tributo, alícuota y moneda)
- Cliente SOAP padrón A4 (`padron/client.py`) — consulta de contribuyentes por CUIT contra `ws_sr_padron_a4`
- 10 tools MCP en `mcp/lookup.py`: 5 de catálogo WSFEv1, 2 de padrón (`get_taxpayer_details`, `validate_taxpayer_status`), 3 de validación pura (`validate_invoice_type`, `validate_vat_condition`, `validate_currency`)
- Validaciones puras de catálogos AFIP sin red (`validation/catalogs.py`) — tipos de comprobante, condiciones IVA y monedas hardcodeados
- Tests E2E opt-in en `tests/e2e/test_lookup_e2e.py` con `pytest.mark.e2e` — skip automático si no hay cert/key/CUIT configurados

### Changed (breaking)
- **7 tools MCP ahora aceptan `cert_path` / `key_path` como overrides opcionales** en lugar de parámetros requeridos. Si no se pasan, el resolver central (`resolve_runtime_config`) los toma de `Settings` (env vars `ARCA_CERT_PATH` / `ARCA_KEY_PATH`). Si tampoco están en Settings, la tool retorna `ArcaError` con causa `MISSING_CONFIG` en lugar de fallar con error de parámetro.
- Overrides parciales (solo `cert_path` o solo `key_path`) retornan `ArcaError` con causa `INVALID_CONFIG_OVERRIDE`.
- `environment="produccion"` en cualquier tool retorna `ArcaError` con causa `UNSUPPORTED_ENVIRONMENT` (v0.2 solo soporta homologación).
- Las tools afectadas: `validate_certificate`, `validate_private_key`, `validate_cert_key_match`, `inspect_certificate`, `validate_wsaa_login`, `validate_service_authorization`, `setup_doctor`.

### Tests
- 292 tests pasando (293 collected, 1 skipped — E2E sin credenciales)

## [0.1.2] - 2026-05-18

### Added
- **E2E test opt-in contra `wsaahomo.afip.gov.ar`** (`tests/test_e2e_wsaa.py`) — cierra el último criterio pendiente de v0.1. Skip automático si `ARCA_TEST_CERT_PATH` / `ARCA_TEST_KEY_PATH` no están seteados. Marker `e2e` para excluirlo del run normal (`pytest -m "not e2e"`).
- Test de regresión: SOAP Fault dentro de HTTP 500 se parsea correctamente (`test_call_login_cms_parses_soap_fault_inside_http_500`).
- Test: "El CEE ya posee un TA valido" se interpreta como éxito (`test_login_ta_already_valid_is_success`).

### Changed
- **`call_login_cms` parsea SOAP Faults dentro de HTTP 500** antes de `raise_for_status()`. Antes perdíamos el faultstring legible (AFIP devuelve detalles como "Computador no autorizado a acceder al servicio" dentro del 500). Esto cumple el principio del CLAUDE.md de transformar errores opacos en mensajes legibles.
- **`run_setup_doctor` no hace llamada redundante a WSAA** para `service_authorization`. La autorización se deriva del éxito de `wsaa_login` para el mismo servicio. Antes, la segunda llamada rompía con "El CEE ya posee un TA valido" porque AFIP rate-limita TA requests.
- **`validate_wsaa_login` interpreta "ya posee un TA valido" como éxito** (sin token, con mensaje explicativo). Resolución definitiva requiere caché de token, planificada para v0.3.

### Tests
- 71 → 74 unit tests (todos verdes)
- 1 E2E test opt-in verificado contra wsaahomo real (5/5 checks ✅)

## [0.1.1] - 2026-05-17

### Added
- `docs/ROADMAP.md` — fuente de verdad del roadmap con criterios de aceptación por versión
- Tests adicionales: validación de private key encriptada con password, retry de WSAA, formato ISO 8601 del TRA, environment resolver
- 71 tests pasando (antes 64)

### Changed
- **Tools MCP aceptan `environment` per-call** (`"homologacion"` por default, `"produccion"` válido) — antes hardcodeaban homologación. Fix de bug B2.
- **`call_login_cms` usa `httpx.Client(verify=True)` con retry** de errores transitorios (`ConnectError`, `TimeoutException`). Antes usaba `httpx.post` sin cliente. Fix de bug B3.
- **TRA usa `isoformat(timespec="seconds")`** en lugar de offset hardcodeado `-00:00`. Ahora es ISO 8601 / RFC 3339 estricto. Fix de bug B4.
- **`validate_*` capturan `Exception` defensivamente** para evitar que excepciones inesperadas de `cryptography` crasheen el server MCP. Fix de bug B5.
- `CLAUDE.md` actualizado con el roadmap nuevo (v1 Lookup Layer en vez de WSAA productivo) alineado con el diseño estratégico
- `__version__` bumpeado a `0.1.1` en `pyproject.toml` y `src/arca_mcp/__init__.py`

### Removed
- Singleton global `settings = Settings()` en `config.py` (era código muerto, violaba principio de no usar singletons). Fix de bug B1.

## [0.1.0] - 2026-05-16

### Added
- **v0 Setup Doctor completo** — 7 tools MCP funcionales para diagnóstico de setup ARCA
- Carga y validación de certificados X509 y private keys RSA
- `validate_certificate`, `validate_private_key`, `validate_cert_key_match`, `inspect_certificate`
- `validate_wsaa_login` — autenticación contra WSAA homologación (CMS signing + SOAP)
- `validate_service_authorization` con enum `ArcaService` para servicios conocidos
- `setup_doctor` — orquestador con short-circuit graceful y reporte estructurado
- Capa de errores estructurados con enum `ArcaErrorCause`
- Docker multi-stage con volumen externo para certificados
- 64 tests automatizados pasando
- Documentación: overview técnico y resumen ejecutivo v0

### Changed
- Reemplazada dependencia `pyafipws` (rota en Python 3.12+) por implementación directa de WSAA con `cryptography` + `httpx`

### Known issues
- Criterio E2E pendiente: no hay test automatizado contra `wsaahomo.afip.gov.ar`. Se cerrará como `v0.1.2` antes de avanzar a `v0.2.0` (ver `docs/ROADMAP.md`).
