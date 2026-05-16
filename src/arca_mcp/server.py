import os

import fastmcp

from arca_mcp.mcp import certificates, setup

mcp = fastmcp.FastMCP(
    name="arca-mcp",
    instructions=(
        "Servidor MCP para operaciones fiscales ARCA/AFIP. "
        "Determinista y seguro. Acciones irreversibles requieren confirmación explícita."
    ),
)

mcp.mount(certificates.server)
mcp.mount(setup.server)


def main() -> None:
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport == "http":
        mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
