# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

_Próxima entrega: `v0.1.2` (cierre del criterio E2E de v0.1 contra wsaahomo) o `v0.2.0` (Lookup Layer)._

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
