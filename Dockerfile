FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

COPY pyproject.toml .
RUN uv sync --no-install-project --no-dev

COPY src/ src/
RUN uv sync --no-dev


FROM python:3.12-slim-bookworm

WORKDIR /app

COPY --from=builder /app/.venv .venv
COPY --from=builder /app/src src/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"

# Certificados se montan como volumen externo, nunca en la imagen
VOLUME ["/certs"]

EXPOSE 8000

CMD ["python", "-m", "arca_mcp.server"]
