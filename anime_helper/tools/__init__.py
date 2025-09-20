"""MCP tools for AnimeHelper."""

# Import all tools to register them with FastMCP
from . import search
from . import details
from . import trending
from . import airing
from . import cache_tools
from . import nlp
from . import meta

__all__ = [
    "search",
    "details", 
    "trending",
    "airing",
    "cache_tools",
    "nlp",
    "meta"
]
