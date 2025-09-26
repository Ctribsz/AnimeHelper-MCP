"""Trending and seasonal tools for AnimeHelper-MCP."""

from datetime import datetime, timezone
from typing import Optional, List
import requests

from ..core.cache import gql
from ..core.http_client import err_payload
from ..core.normalizers import norm_hit_from_anilist
from ..utils.helpers import season_from_month

def trending(kind: str = "ANIME", limit: int = 10, format_in: Optional[List[str]] = None):
    """Top trending (AniList). Opcional: format_in=['MOVIE','TV','OVA','ONA','SPECIAL']"""
    src = "anilist"
    try:
        kind = kind.upper()
        limit = min(max(limit, 1), 25)
        formats = [f.upper() for f in (format_in or [])] or None
        
        try:
            # Intentar AniList primero
            q = """
            query ($type: MediaType, $per: Int, $formats: [MediaFormat!]){
              Page(perPage: $per){
                media(type:$type, sort: TRENDING_DESC, format_in: $formats){
                  id idMal siteUrl format episodes chapters averageScore seasonYear
                  title { romaji english native }
                }
              }
            }"""
            data = gql(q, {"type": kind, "per": limit, "formats": formats})
            hits = [norm_hit_from_anilist(m) for m in data["Page"]["media"]]
            return {"schemaVersion": "1.0.0", "kind": kind, "format_in": formats, "results": hits[:limit]}
            
        except Exception as anilist_error:
            # Si AniList falla, usar Jikan como fallback
            print(f"AniList trending failed: {anilist_error}, falling back to Jikan")
            
            from ..core.http_client import http_get
            import urllib.parse
            from ..models.types import MediaHit
            
            base = "https://api.jikan.moe/v4/anime" if kind == "ANIME" else "https://api.jikan.moe/v4/manga"
            params = {"order_by": "popularity", "limit": str(limit)}
            url = base + "?" + urllib.parse.urlencode(params)
            
            r = http_get(url)
            payload = r.json()
            
            results = []
            for item in payload.get("data", []):
                score = item.get("score")
                results.append({
                    "source": "jikan",
                    "id": item.get("mal_id"),
                    "idMal": item.get("mal_id"),
                    "titles": {
                        "romaji": item.get("title"),
                        "english": item.get("title_english"),
                        "native": None
                    },
                    "year": item.get("year"),
                    "format": (item.get("type") or "").upper(),
                    "episodes": item.get("episodes") if kind == "ANIME" else None,
                    "chapters": item.get("chapters") if kind == "MANGA" else None,
                    "score": int(score * 10) if isinstance(score, (int, float)) else None,
                    "url": item.get("url")
                })
            
            return {
                "schemaVersion": "1.0.0", 
                "kind": kind, 
                "format_in": formats, 
                "results": results[:limit],
                "source": "jikan_fallback"
            }
            
    except requests.Timeout:
        return err_payload(src, "TIMEOUT", "Upstream timed out")
    except Exception as e:
        return err_payload(src, "UNEXPECTED", str(e))


def season_top(kind: str = "ANIME", season: str | None = None, year: int | None = None,
               sort: str = "TRENDING_DESC", limit: int = 10, format_in: Optional[List[str]] = None):
    """
    Top de una temporada (por defecto, temporada/año actuales).
    kind: ANIME|MANGA (AniList solo soporta season para ANIME; MANGA usa trending).
    format_in: ej. ['MOVIE'] para películas de la temporada.
    """
    try:
        limit = min(max(limit, 1), 25)
        kind = kind.upper()
        now = datetime.now(timezone.utc)
        sea = (season or season_from_month(now.month)).upper()
        yr = int(year or now.year)
        formats = [f.upper() for f in (format_in or [])] or None

        if kind == "ANIME":
            try:
                # Intentar AniList primero
                q = """
                query ($type: MediaType!, $season: MediaSeason!, $year: Int!, $per: Int!, $sort: [MediaSort!]!, $formats:[MediaFormat!]) {
                  Page(perPage: $per) {
                    media(type: $type, season: $season, seasonYear: $year, sort: $sort, format_in: $formats) {
                      id idMal siteUrl format episodes averageScore seasonYear
                      title { romaji english native }
                    }
                  }
                }"""
                data = gql(q, {"type": "ANIME", "season": sea, "year": yr, "per": limit, "sort": [sort], "formats": formats})
                hits = [norm_hit_from_anilist(m) for m in data["Page"]["media"]]
                return {"schemaVersion": "1.0.0", "kind": "ANIME", "season": sea, "year": yr, "sort": sort, "format_in": formats, "results": hits[:limit]}
                
            except Exception as anilist_error:
                # Fallback a Jikan para anime de temporada
                print(f"AniList season_top failed: {anilist_error}, falling back to Jikan")
                
                from ..core.http_client import http_get
                import urllib.parse
                
                # Jikan no tiene filtro por temporada exacta, usamos popular del año
                base = "https://api.jikan.moe/v4/anime"
                params = {"order_by": "popularity", "limit": str(limit)}
                
                # Si tenemos año específico, agregarlo como filtro
                if yr and yr >= 2000:
                    params["start_date"] = f"{yr}-01-01"
                    params["end_date"] = f"{yr}-12-31"
                
                url = base + "?" + urllib.parse.urlencode(params)
                r = http_get(url)
                payload = r.json()
                
                results = []
                for item in payload.get("data", []):
                    score = item.get("score")
                    results.append({
                        "source": "jikan",
                        "id": item.get("mal_id"),
                        "idMal": item.get("mal_id"),
                        "titles": {
                            "romaji": item.get("title"),
                            "english": item.get("title_english"),
                            "native": None
                        },
                        "year": item.get("year"),
                        "format": (item.get("type") or "").upper(),
                        "episodes": item.get("episodes"),
                        "chapters": None,
                        "score": int(score * 10) if isinstance(score, (int, float)) else None,
                        "url": item.get("url")
                    })
                
                return {
                    "schemaVersion": "1.0.0", 
                    "kind": "ANIME", 
                    "season": sea, 
                    "year": yr, 
                    "sort": "popularity", 
                    "format_in": formats, 
                    "results": results[:limit],
                    "source": "jikan_fallback"
                }

        # Para MANGA no hay season en AniList; usamos trending como proxy
        try:
            q = """
            query ($type: MediaType!, $per: Int!) {
              Page(perPage: $per) {
                media(type:$type, sort: TRENDING_DESC){
                  id idMal siteUrl format chapters averageScore
                  title { romaji english native }
                }
              }
            }"""
            data = gql(q, {"type": "MANGA", "per": limit})
            hits = [norm_hit_from_anilist(m) for m in data["Page"]["media"]]
            return {"schemaVersion": "1.0.0", "kind": "MANGA", "season": None, "year": None, "sort": "TRENDING_DESC", "results": hits[:limit]}
            
        except Exception as anilist_error:
            # Fallback para MANGA
            print(f"AniList manga trending failed: {anilist_error}, falling back to Jikan")
            
            from ..core.http_client import http_get
            import urllib.parse
            
            base = "https://api.jikan.moe/v4/manga"
            params = {"order_by": "popularity", "limit": str(limit)}
            url = base + "?" + urllib.parse.urlencode(params)
            
            r = http_get(url)
            payload = r.json()
            
            results = []
            for item in payload.get("data", []):
                score = item.get("score")
                results.append({
                    "source": "jikan",
                    "id": item.get("mal_id"),
                    "idMal": item.get("mal_id"),
                    "titles": {
                        "romaji": item.get("title"),
                        "english": item.get("title_english"),
                        "native": None
                    },
                    "year": item.get("published", {}).get("from", "").split("-")[0] if item.get("published") else None,
                    "format": (item.get("type") or "").upper(),
                    "episodes": None,
                    "chapters": item.get("chapters"),
                    "score": int(score * 10) if isinstance(score, (int, float)) else None,
                    "url": item.get("url")
                })
            
            return {
                "schemaVersion": "1.0.0", 
                "kind": "MANGA", 
                "season": None, 
                "year": None, 
                "sort": "popularity", 
                "results": results[:limit],
                "source": "jikan_fallback"
            }
            
    except requests.Timeout:
        return err_payload("anilist", "TIMEOUT", "Upstream timed out")
    except requests.HTTPError as e:
        sc = getattr(e, "response", None).status_code if getattr(e, "response", None) else 0
        return err_payload("anilist", f"UPSTREAM_{sc}", str(e))
    except Exception as e:
        return err_payload("anilist", "UNEXPECTED", str(e))


def register_tools(mcp):
    mcp.tool()(trending)
    mcp.tool()(season_top)