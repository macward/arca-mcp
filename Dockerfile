FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

COPY pyproject.toml README.md LICENSE ./
RUN uv sync --no-install-project --no-dev

COPY src/ src/
RUN uv sync --no-dev


FROM python:3.12-slim-bookworm

WORKDIR /app

RUN useradd --create-home --uid 1000 --shell /bin/bash arca

COPY --from=builder --chown=arca:arca /app/.venv .venv
COPY --from=builder --chown=arca:arca /app/src src/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"

# Certificados se montan como volumen externo, nunca en la imagen.
# Si el host monta /certs con UID distinto a 1000, ajustar permisos o UID en el host.
VOLUME ["/certs"]

EXPOSE 8000

USER arca

CMD ["python", "-m", "arca_mcp.server"]
