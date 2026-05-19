# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `create_voucher_draft` — creates a draft invoice in PENDING state; no fiscal operation is performed until the flow is completed
- `validate_voucher_draft` — validates draft against fiscal policy rules; transitions to VALIDATED on success, stays PENDING on errors with violation details
- `confirm_voucher_creation` — submits validated draft to WSFEv1 (FECAESolicitar), retrieves CAE, marks draft CONFIRMED; idempotency_key prevents double emission
- `get_last_voucher_number` — queries last authorized voucher number for a given punto_venta and cbte_tipo
- `get_voucher_info` — retrieves full details of a specific voucher from WSFEv1

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
