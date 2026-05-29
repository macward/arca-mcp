# Contributing to arca-mcp

Gracias por interesarte en contribuir. Este documento describe cómo levantar el proyecto, correr tests y enviar cambios.

## Prerequisitos

- Python 3.12 o 3.13
- [uv](https://docs.astral.sh/uv/) para manejar dependencias y virtualenv
- (Opcional para tests E2E) Certificado y clave de homologación ARCA

## Setup

```bash
git clone https://github.com/macward/arca-mcp
cd arca-mcp
uv sync
```

Eso instala dependencias de runtime + dev en `.venv/`.

## Correr tests

Suite completa sin red:

```bash
uv run pytest -m "not e2e"
```

Tests E2E contra `wsaahomo.afip.gov.ar` (requieren credenciales reales de homologación):

```bash
ARCA_TEST_CERT_PATH=/path/to/homo.crt \
ARCA_TEST_KEY_PATH=/path/to/homo.key \
uv run pytest -m e2e
```

Lint:

```bash
uv run ruff check .
```

## Reportar bugs

Abrí un [issue](https://github.com/macward/arca-mcp/issues) con:

- Versión (`pip show arca-mcp` o commit SHA).
- Stack trace o respuesta MCP completa, sanitizando datos sensibles (CUIT, claves, tokens).
- Ambiente: `homologacion` o `produccion`, y SO.
- Pasos mínimos para reproducir.

Para vulnerabilidades de seguridad, **no abras issue público**: ver [SECURITY.md](SECURITY.md).

## Flujo de Pull Request

1. Fork + branch desde `main`. Nombre sugerido: `fix/<descripción>`, `feat/<descripción>`, `chore/<descripción>`.
2. Hacé el cambio acotado al scope del issue. Evitá mezclar refactors no relacionados.
3. Agregá o actualizá tests. Toda lógica nueva debe tener cobertura (excepto wiring trivial).
4. Verificá local: `uv run pytest -m "not e2e"` y `uv run ruff check .` deben pasar.
5. Actualizá `CHANGELOG.md` bajo `## [Unreleased]` con una línea descriptiva en la sección correspondiente (Added/Changed/Fixed/Security).
6. Commit message: prefijo tipo Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`), un cuerpo breve explicando el "por qué".
7. Abrí el PR contra `main`. Describí qué problema resuelve y cómo testeaste el cambio.

## Principios de diseño

Antes de proponer cambios mayores, leé el [CLAUDE.md](CLAUDE.md) — especialmente las secciones de **Determinismo**, **Human in the Loop**, **Seguridad** e **Idempotencia**. PRs que violen estos principios serán rechazados o requerirán rediseño.

Puntos clave:

- La private key **nunca** debe aparecer en respuestas MCP, logs o errores.
- Operaciones irreversibles (emisión de comprobantes) siguen `draft → validate → confirm`. No agregues atajos.
- Homologación y producción son ambientes separados en configuración. No mezclar.
- Toda operación irreversible requiere `idempotency_key`.

## Código de conducta

Al contribuir aceptás respetar el [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
