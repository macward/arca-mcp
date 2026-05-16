# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
