# SPDX-License-Identifier: MIT
"""
AnimeHelper-MCP server entrypoint (modularized).

This minimal server wires FastMCP with all tool modules under anime_helper/tools/.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

# Import tool modules (each provides register_tools(mcp))
from .tools import search, details, trending, airing, cache_tools, nlp, meta, resolve


def create_app() -> FastMCP:
    mcp = FastMCP("anime-helper")

    # Register tools from each module
    search.register_tools(mcp)
    details.register_tools(mcp)
    trending.register_tools(mcp)
    airing.register_tools(mcp)
    cache_tools.register_tools(mcp)
    nlp.register_tools(mcp)
    meta.register_tools(mcp)
    resolve.register_tools(mcp)
    
    return mcp


if __name__ == "__main__":
    app = create_app()
    app.run()
