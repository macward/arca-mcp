import logging
import os

import fastmcp
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from arca_mcp.config import init_server_settings
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

    async def dispatch(self, request: Request, call_next):
        expected = os.environ.get("ARCA_API_KEY")
        if expected:
            provided = request.headers.get("x-api-key") or request.headers.get(
                "authorization", ""
            ).removeprefix("Bearer ").strip()
            if provided != expected:
                return Response("Unauthorized", status_code=401)
        return await call_next(request)


def main() -> None:
    settings = init_server_settings()
    logger.info(
        "arca-mcp iniciado | environment=%s cert_path=%s key_configured=%s cuit=%s",
        settings.environment,
        settings.cert_path,
        bool(settings.key_path),
        settings.cuit,
    )

    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport == "http":
        host = os.getenv("ARCA_HTTP_HOST", "127.0.0.1")
        port = int(os.getenv("ARCA_HTTP_PORT", "8000"))
        mcp.run(
            transport="streamable-http",
            host=host,
            port=port,
            middleware=[Middleware(_ApiKeyMiddleware)],
        )
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
