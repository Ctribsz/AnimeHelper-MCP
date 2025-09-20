"""Metadata and help tools for AnimeHelper-MCP."""

from importlib.metadata import version, PackageNotFoundError

# Version info
try:
    __VERSION__ = version("anime-helper")   # nombre del paquete en pyproject
except PackageNotFoundError:
    __VERSION__ = "0.0.0+dev"

def health():
    """Health check endpoint."""
    return {"schemaVersion": "1.0.0", "ok": True, "sources": ["anilist", "jikan"]}

def help():
    """
    Casos de uso y ejemplos de invocación (para hosts y usuarios).
    """
    return {
        "schemaVersion": "1.0.0",
        "name": "anime-helper",
        "version": __VERSION__,
        "summary": "Consulta de Anime & Manga vía AniList (sin key) con fallback Jikan.",
        "features": [
            "ask: NL → season_top / trending / search / details / airing_status / count / what_is",
            "search_media: búsqueda por título (ANIME/MANGA)",
            "media_details: ficha normalizada + recomendaciones",
            "trending(format_in): top en tendencia (MOVIE/TV/OVA/ONA/SPECIAL)",
            "season_top(format_in): top de la temporada actual (ANIME); soporta MOVIE",
            "airing_status: último/próximo episodio (ANIME)",
            "airing_calendar: próximos episodios a emitirse",
            "resolve_title: obtiene IDs canónicos AniList/MAL",
            "cache_info / cache_clear: cache interno GQL"
        ],
        "examples": [
            { "title": "Pregunta NL", "prompt": "¿En qué capítulo va One Piece?" },
            { "title": "Temporada actual", "prompt": "¿Cuáles son los animes más llamativos de esta temporada?" },
            { "title": "Películas de esta temporada", "prompt": "anime-helper__season_top {\"kind\":\"ANIME\",\"format_in\":[\"MOVIE\"],\"limit\":5}" },
            { "title": "Tendencias (MANGA)", "prompt": "anime-helper__trending {\"kind\":\"MANGA\",\"limit\":5}" },
            { "title": "Calendario 7 días", "prompt": "anime-helper__airing_calendar {\"days\":7}" },
            { "title": "Resolver título", "prompt": "anime-helper__resolve_title {\"title\":\"Vinland Saga\"}" },
            { "title": "Detalles", "prompt": "Dame la ficha de Vinland Saga" },
            { "title": "Búsqueda directa", "prompt": "anime-helper__search_media {\"query\":\"one piece\",\"kind\":\"ANIME\",\"limit\":3}" }
        ],
        "notes": [
            "Sin API key (AniList/Jikan). Respeta rate limits.",
            "Siempre devuelve schemaVersion en OK y en error.",
            "IDs: AniList en media_details/airing_status; para MAL usa source='jikan'."
        ]
    }

def help_text():
    """Versión en texto plano de la ayuda (útil para hosts minimalistas)."""
    return (
        "anime-helper · Qué puedo hacer:\n"
        "- ask(text): NL (ES/EN). Ej: '¿En qué capítulo va One Piece?'\n"
        "- season_top(kind='ANIME', limit=10, format_in=['MOVIE']): top de la temporada (ej. películas).\n"
        "- trending(kind, limit, format_in): tendencias actuales.\n"
        "- search_media(query, kind): buscar por título.\n"
        "- media_details(source, id, kind): ficha completa.\n"
        "- airing_status(query|anilist_id): último/próximo episodio.\n"
        "- airing_calendar(days): próximos episodios a emitirse.\n"
        "- resolve_title(title): IDs canónicos AniList/MAL.\n"
        "- cache_info / cache_clear: cache GQL.\n"
    )

def about():
    """About information for the service."""
    return {
        "schemaVersion": "1.0.0",
        "name": "anime-helper",
        "version": __VERSION__,
        "endpoints": {"anilist": "https://graphql.anilist.co", "jikan": "https://api.jikan.moe/v4"},
        "limits": {"maxPerPage": 25, "timeoutSec": 15}
    }


def register_tools(mcp):
    """Register meta/help tools with FastMCP."""
    mcp.tool()(health)
    mcp.tool()(help)
    mcp.tool()(help_text)
    mcp.tool()(about)
