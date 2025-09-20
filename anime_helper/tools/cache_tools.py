"""Cache management tools for AnimeHelper-MCP."""

from ..core.cache import cache_info as _cache_info, cache_clear as _cache_clear

def cache_info():
    """Estadísticas simples del cache GQL."""
    info = _cache_info()
    info["schemaVersion"] = "1.0.0"
    return info

def cache_clear():
    """Limpia el cache GQL."""
    cleared = _cache_clear()
    return {"schemaVersion": "1.0.0", "cleared": cleared}


def register_tools(mcp):
    """Register cache-related tools with FastMCP."""
    mcp.tool()(cache_info)
    mcp.tool()(cache_clear)
