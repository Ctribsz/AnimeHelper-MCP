"""Airing schedule tools for AnimeHelper-MCP."""

from datetime import datetime, timezone
from typing import Optional, List
import requests

from ..core.cache import gql
from ..core.http_client import err_payload
from ..core.normalizers import norm_title
from ..models.types import AiringItem


def airing_status(anilist_id: Optional[int] = None, query: Optional[str] = None):
    """
    Estado de emisión (ANIME): último emitido ('last') y próximo ('next').
    Usa anilist_id o resuelve por 'query' (primer match).
    """
    try:
        mid = anilist_id
        if mid is None:
            if not query:
                return err_payload("anilist", "BAD_REQUEST", "Provide anilist_id or query")
            q = """
            query ($q:String){
              Page(perPage:1){ media(search:$q, type:ANIME, sort:[SEARCH_MATCH,POPULARITY_DESC]){ id } }
            }"""
            data = gql(q, {"q": query})
            media = data["Page"]["media"]
            if not media:
                return {"schemaVersion": "1.0.0", "query": query, "status": "NOT_FOUND"}
            mid = media[0]["id"]

        q2 = """
        query ($id:Int){
          Media(id:$id, type:ANIME){
            id siteUrl title{romaji english native}
            nextAiringEpisode{ episode airingAt }
            airingSchedule(notYetAired:false, perPage:1, sort:TIME_DESC){
              nodes{ episode airingAt }
            }
          }
        }"""
        data2 = gql(q2, {"id": mid})
        m = data2["Media"]
        last_node = (m.get("airingSchedule") or {}).get("nodes") or []
        last = last_node[0] if last_node else None
        nxt = m.get("nextAiringEpisode")
        return {
            "schemaVersion": "1.0.0",
            "id": m["id"],
            "titles": norm_title(m.get("title", {})),
            "url": m.get("siteUrl"),
            "last": {"episode": last.get("episode"), "airingAt": last.get("airingAt")} if last else None,
            "next": {"episode": nxt.get("episode"), "airingAt": nxt.get("airingAt")} if nxt else None
        }
    except requests.Timeout:
        return err_payload("anilist", "TIMEOUT", "Upstream timed out")
    except requests.HTTPError as e:
        sc = getattr(e, "response", None).status_code if getattr(e, "response", None) else 0
        return err_payload("anilist", f"UPSTREAM_{sc}", str(e))
    except Exception as e:
        return err_payload("anilist", "UNEXPECTED", str(e))


def airing_calendar(days: int = 7, per_page: int = 50):
    """
    Próximos episodios a emitirse (siguientes 'days' días), ordenados por tiempo asc.
    """
    try:
        days = max(1, min(30, int(days)))
        per = max(1, min(50, int(per_page)))
        now = int(datetime.now(timezone.utc).timestamp())
        until = now + days * 86400
        q = """
        query ($from: Int!, $to: Int!, $per:Int!){
          Page(perPage: $per){
            airingSchedules(airingAt_greater: $from, airingAt_lesser: $to, sort: TIME){
              episode airingAt
              media{
                id idMal siteUrl format title{romaji english native}
              }
            }
          }
        }"""
        data = gql(q, {"from": now, "to": until, "per": per})
        items: List[AiringItem] = []
        for node in (data.get("Page") or {}).get("airingSchedules", []):
            m = node.get("media") or {}
            items.append({
                "when": node.get("airingAt"),
                "episode": node.get("episode"),
                "media": {
                    "source": "anilist",
                    "id": m.get("id"),
                    "idMal": m.get("idMal"),
                    "titles": norm_title(m.get("title", {})),
                    "year": None,
                    "format": m.get("format"),
                    "episodes": None,
                    "chapters": None,
                    "score": None,
                    "url": m.get("siteUrl"),
                }
            })
        return {"schemaVersion": "1.0.0", "days": days, "results": items}
    except requests.Timeout:
        return err_payload("anilist", "TIMEOUT", "Upstream timed out")
    except requests.HTTPError as e:
        sc = getattr(e, "response", None).status_code if getattr(e, "response", None) else 0
        return err_payload("anilist", f"UPSTREAM_{sc}", str(e))
    except Exception as e:
        return err_payload("anilist", "UNEXPECTED", str(e))


def register_tools(mcp):
    mcp.tool()(airing_status)
    mcp.tool()(airing_calendar)