import hmac
import logging
import os

import fastmcp
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from arca_mcp.config import init_server_settings
from arca_mcp.invoicing.idempotency import IdempotencyStore
from arca_mcp.mcp import certificates, invoicing, lookup, setup

logger = logging.getLogger(__name__)

mcp = fastmcp.FastMCP(
    name="arca-mcp",
    instructions=(
        "Servidor MCP para operaciones fiscales ARCA/AFIP. "
        "Determinista y seguro. Acciones irreversibles requieren confirmación explícita."
    ),
)

mcp.mount(certificates.server)
mcp.mount(setup.server)
mcp.mount(lookup.server)
mcp.mount(invoicing.server)


class _ApiKeyMiddleware(BaseHTTPMiddleware):
    """Rechaza requests sin API key cuando ARCA_API_KEY está configurada."""

    def __init__(self, app, expected: str | None = None):
        super().__init__(app)
        self._expected = expected

    async def dispatch(self, request: Request, call_next):
        if self._expected:
            x_api_key = request.headers.get("x-api-key", "")
            auth_parts = request.headers.get("authorization", "").split()
            bearer_token = (
                auth_parts[1]
                if len(auth_parts) == 2 and auth_parts[0].lower() == "bearer"
                else ""
            )
            provided = x_api_key or bearer_token  # x-api-key takes precedence over Authorization: Bearer
            if not hmac.compare_digest(provided, self._expected):
                return Response("Unauthorized", status_code=401)
        return await call_next(request)


def main() -> None:
    # Recover from crashes: delete PENDING idempotency entries older than 5 min
    # that were left behind by a previous process that died mid-emission.
    _store = IdempotencyStore()
    stale = _store.cleanup_stale_pending()
    if stale:
        logger.warning("startup: eliminadas %d entradas PENDING obsoletas del IdempotencyStore", stale)
    _store.close()

    settings = init_server_settings()
    logger.info(
        "arca-mcp iniciado | environment=%s cert_configured=%s key_configured=%s cuit=%s",
        settings.environment,
        bool(settings.cert_path),
        bool(settings.key_path),
        settings.cuit,
    )

    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport == "http":
        api_key = os.environ.get("ARCA_API_KEY") or None
        host = os.getenv("ARCA_HTTP_HOST", "127.0.0.1")
        port = int(os.getenv("ARCA_HTTP_PORT", "8000"))
        mcp.run(
            transport="streamable-http",
            host=host,
            port=port,
            middleware=[Middleware(_ApiKeyMiddleware, expected=api_key)],
        )
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
