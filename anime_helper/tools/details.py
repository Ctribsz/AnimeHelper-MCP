"""Media details tools for AnimeHelper-MCP."""

import requests
from ..core.cache import gql
from ..core.http_client import http_get, err_payload
from ..core.normalizers import norm_details_from_anilist
from ..models.types import Details


def media_details(source: str, id: int, kind: str = "ANIME") -> Details:
    """Ficha completa normalizada. source: 'anilist' (id AniList) o 'jikan' (id MAL)."""
    src = source
    try:
        kind = kind.upper()
        if source == "anilist":
            q = """
            query ($id: Int, $type: MediaType){
              Media(id: $id, type: $type) {
                id idMal siteUrl format status episodes chapters averageScore
                genres description(asHtml:false) title { romaji english native }
                tags { name } externalLinks { site url }
                recommendations(sort: RATING_DESC, perPage: 10) {
                  nodes { mediaRecommendation {
                    id idMal siteUrl format episodes chapters averageScore seasonYear
                    startDate { year } title { romaji english native }
                  }}
                }
              }
            }"""
            data = gql(q, {"id": id, "type": kind})
            det = norm_details_from_anilist(data["Media"])
            det["schemaVersion"] = "1.0.0"
            return det

        base = "https://api.jikan.moe/v4/anime/" if kind == "ANIME" else "https://api.jikan.moe/v4/manga/"
        r = http_get(base + str(id))
        r.raise_for_status()
        d = r.json().get("data", {})
        titles = {"romaji": d.get("title"), "english": d.get("title_english"), "native": None}
        genres = [g.get("name") for g in d.get("genres", [])]
        score10 = d.get("score")
        return {
            "schemaVersion": "1.0.0",
            "source": "jikan",
            "id": d.get("mal_id"),
            "idMal": d.get("mal_id"),
            "titles": titles,
            "format": (d.get("type") or "").upper(),
            "status": (d.get("status") or "").upper(),
            "episodes": d.get("episodes") if kind == "ANIME" else None,
            "chapters": d.get("chapters") if kind == "MANGA" else None,
            "genres": genres,
            "tags": [],
            "score": {"anilist": None, "mal": int(score10 * 10) if isinstance(score10, (int, float)) else None},
            "synopsis": d.get("synopsis") or "",
            "url": d.get("url"),
            "external": [{"site": "MAL", "url": d.get("url")}],
            "recommendations": []
        }

    except requests.Timeout:
        return err_payload(src, "TIMEOUT", "Upstream timed out")
    except requests.HTTPError as e:
        sc = getattr(e, "response", None).status_code if getattr(e, "response", None) else 0
        return err_payload(src, f"UPSTREAM_{sc}", str(e))
    except Exception as e:
        return err_payload(src, "UNEXPECTED", str(e))


def register_tools(mcp):
    mcp.tool()(media_details)