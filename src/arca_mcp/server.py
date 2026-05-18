import logging
import os

import fastmcp

from arca_mcp.config import init_server_settings
from arca_mcp.mcp import certificates, lookup, setup

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


def main() -> None:
    # Cargar Settings desde ARCA_* env vars y .env al arrancar.
    # El singleton queda disponible para el resolver durante toda la vida del proceso.
    settings = init_server_settings()
    logger.info(
        "arca-mcp iniciado | environment=%s cert_path=%s key_path=%s cuit=%s",
        settings.environment,
        settings.cert_path,
        settings.key_path,
        settings.cuit,
    )

    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport == "http":
        mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
