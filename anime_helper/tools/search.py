"""Search tools for AnimeHelper-MCP."""

import urllib.parse
from typing import List, Dict, Any, Optional
import requests

from ..core.cache import gql
from ..core.http_client import http_get, err_payload
from ..core.normalizers import norm_hit_from_anilist
from ..models.types import MediaHit

def search_media(
    query: str,
    kind: str = "ANIME",
    source: str = "anilist",
    limit: int = 5,
    format_in: Optional[List[str]] = None,
):
    """
    Busca ANIME o MANGA.
    source: 'anilist' (default) o 'jikan' (fallback).
    format_in: lista opcional de formatos (p.ej. ['MOVIE','TV','OVA','ONA','SPECIAL'])
    """
    src = source
    try:
        kind = kind.upper()
        limit = min(max(limit, 1), 25)
        formats = [f.upper() for f in (format_in or [])] or None

        if source == "anilist":
            try:
                q = """
                query ($q: String, $type: MediaType, $per: Int, $formats:[MediaFormat!]) {
                  Page(perPage: $per) {
                    media(
                      search: $q,
                      type: $type,
                      sort: [SEARCH_MATCH, POPULARITY_DESC],
                      format_in: $formats
                    ) {
                      id idMal siteUrl format episodes chapters averageScore seasonYear
                      startDate { year } title { romaji english native }
                    }
                  }
                }"""
                data = gql(q, {"q": query, "type": kind, "per": limit, "formats": formats})
                hits = [norm_hit_from_anilist(m) for m in data["Page"]["media"]]
                return {
                    "schemaVersion": "1.0.0",
                    "query": query,
                    "kind": kind,
                    "source": "anilist",
                    "format_in": formats,
                    "results": hits[:limit],
                }
            except Exception as anilist_error:
                # Si AniList falla, usar Jikan automáticamente
                print(f"AniList failed: {anilist_error}, falling back to Jikan")
                source = "jikan"  # Cambiar al fallback

        # Código de Jikan (se ejecuta si source == "jikan" O si AniList falló)
        if source == "jikan":
            jl_map = {"TV": "tv", "MOVIE": "movie", "OVA": "ova", "ONA": "ona", "SPECIAL": "special"}
            jikan_type = None
            if formats:
                for f in formats:
                    if f in jl_map:
                        jikan_type = jl_map[f]
                        break

            base = "https://api.jikan.moe/v4/anime" if kind == "ANIME" else "https://api.jikan.moe/v4/manga"
            params = {"q": query, "limit": str(limit)}
            if jikan_type and kind == "ANIME":
                params["type"] = jikan_type

            url = base + "?" + urllib.parse.urlencode(params)
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

            if formats and kind == "MANGA":
                out = [h for h in out if (h.get("format") or "").upper() in formats]

            return {
                "schemaVersion": "1.0.0",
                "query": query,
                "kind": kind,
                "source": "jikan",
                "format_in": formats,
                "results": out,
            }

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
