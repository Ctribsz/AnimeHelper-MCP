"""Search tools for AnimeHelper-MCP."""

import urllib.parse
from typing import List, Dict, Any
import requests

from ..core.cache import gql
from ..core.http_client import http_get, err_payload
from ..core.normalizers import norm_hit_from_anilist
from ..models.types import MediaHit

def search_media(query: str, kind: str = "ANIME", source: str = "anilist", limit: int = 5):
    """Busca ANIME o MANGA. source: 'anilist' (default) o 'jikan' (fallback)."""
    src = source
    try:
        kind = kind.upper()
        limit = min(max(limit, 1), 25)

        if source == "anilist":
            q = """
            query ($q: String, $type: MediaType, $per: Int) {
              Page(perPage: $per) {
                media(search: $q, type: $type, sort: [SEARCH_MATCH, POPULARITY_DESC]) {
                  id idMal siteUrl format episodes chapters averageScore seasonYear
                  startDate { year } title { romaji english native }
                }
              }
            }"""
            data = gql(q, {"q": query, "type": kind, "per": limit})
            hits = [norm_hit_from_anilist(m) for m in data["Page"]["media"]]
            return {"schemaVersion": "1.0.0", "query": query, "kind": kind, "source": "anilist", "results": hits[:limit]}

        # Fallback Jikan (MAL) sin key
        base = "https://api.jikan.moe/v4/anime" if kind == "ANIME" else "https://api.jikan.moe/v4/manga"
        url = f"{base}?q={urllib.parse.quote(query)}&limit={limit}"
        r = http_get(url)
        payload = r.json()
        out: List[MediaHit] = []
        for it in payload.get("data", []):
            titles = {"romaji": it.get("title"), "english": it.get("title_english"), "native": None}
            score = it.get("score")
            out.append({
                "source": "jikan",
                "id": it.get("mal_id"),
                "idMal": it.get("mal_id"),
                "titles": titles,
                "year": it.get("year"),
                "format": (it.get("type") or "").upper(),
                "episodes": it.get("episodes") if kind == "ANIME" else None,
                "chapters": it.get("chapters") if kind == "MANGA" else None,
                "score": int(score * 10) if isinstance(score, (int, float)) else None,
                "url": it.get("url")
            })
        return {"schemaVersion": "1.0.0", "query": query, "kind": kind, "source": "jikan", "results": out}

    except requests.Timeout:
        return err_payload(src, "TIMEOUT", "Upstream timed out")
    except requests.HTTPError as e:
        sc = getattr(e, "response", None).status_code if getattr(e, "response", None) else 0
        return err_payload(src, f"UPSTREAM_{sc}", str(e))
    except Exception as e:
        return err_payload(src, "UNEXPECTED", str(e))


def resolve_title(title: str, kind: str = "ANIME", limit: int = 5):
    """
    Resuelve 'title' a IDs canónicos (AniList y MAL) con mejores candidatos.
    """
    try:
        kind = kind.upper()
        limit = min(max(limit, 1), 10)
        q = """
        query ($q: String, $type: MediaType, $per: Int) {
          Page(perPage: $per) {
            media(search: $q, type: $type, sort: [SEARCH_MATCH, POPULARITY_DESC]) {
              id idMal siteUrl format averageScore seasonYear
              title { romaji english native }
            }
          }
        }"""
        data = gql(q, {"q": title, "type": kind, "per": limit})
        hits = [norm_hit_from_anilist(m) for m in data["Page"]["media"]]
        best = hits[0] if hits else None
        return {"schemaVersion": "1.0.0", "title": title, "kind": kind, "best": best, "candidates": hits}
    except Exception as e:
        return err_payload("anilist", "UNEXPECTED", str(e))


def register_tools(mcp):
    """Register search-related tools with FastMCP."""
    mcp.tool()(search_media)
    mcp.tool()(resolve_title)
