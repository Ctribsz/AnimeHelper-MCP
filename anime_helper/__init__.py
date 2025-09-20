"""AnimeHelper-MCP package.

Exports the FastMCP app factory `create_app` and registers tool modules.
"""
from .server import create_app

__all__ = ["create_app"]
