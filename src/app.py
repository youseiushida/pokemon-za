from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI

try:
    # FastAPI-MCP is optional at import time to allow the app to boot
    from fastapi_mcp import FastApiMCP  # type: ignore
except Exception:  # pragma: no cover
    FastApiMCP = None  # type: ignore


def create_app() -> FastAPI:
    app = FastAPI(title="pokemon-za MCP", version="0.1.0")

    # Initialize MCP if available
    mcp = None
    if FastApiMCP is not None:
        try:
            mcp = FastApiMCP(app)
            # Mount MCP on default path (/mcp); let FastAPI-MCP manage HTTP/SSE on that endpoint
            if hasattr(mcp, "mount_http"):
                try:
                    mcp.mount_http()
                except Exception:
                    # Fallback: ignore mounting errors to keep REST available
                    pass
            # Also expose SSE endpoint explicitly at /sse if supported
            if hasattr(mcp, "mount_sse"):
                try:
                    mcp.mount_sse(path="/sse")
                except Exception:
                    pass
        except Exception:
            mcp = None

    # Register tools (both MCP and REST fallbacks)
    from src.tools import register_tools

    register_tools(app=app, mcp=mcp)
    # If MCP was created before endpoints, ensure re-registration per FAQ
    if mcp is not None and hasattr(mcp, "setup_server"):
        try:
            mcp.setup_server()
        except Exception:
            pass

    @app.get("/")
    def root():
        return {
            "name": "pokemon-za MCP",
            "mcp": {
                "http": "/mcp",
            },
        }

    return app


app = create_app()


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("src.app:app", host=host, port=port, reload=True)


