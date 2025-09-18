# SPDX-License-Identifier: MIT
from __future__ import annotations
import json, requests
from typing import TypedDict, Optional, List, Dict, Any
from mcp.server.fastmcp import FastMCP
import random, time, requests
from importlib.metadata import version, PackageNotFoundError

try:
    __VERSION__ = version("anime-helper")
except PackageNotFoundError:
    __VERSION__ = "0.0.0+dev"

DEFAULT_TIMEOUT = 15
RETRY_CODES = {429, 500, 502, 503, 504}
mcp = FastMCP("anime-helper")
ANILIST_GQL = "https://graphql.anilist.co"
UA = "anime-helper-mcp/0.1"
SCHEMA = "1.0.0"

# ---------- Tipos ----------
class Title(TypedDict):
    romaji: Optional[str]; english: Optional[str]; native: Optional[str]

class MediaHit(TypedDict):
    source: str; id: int; idMal: Optional[int]; titles: Title
    year: Optional[int]; format: Optional[str]; episodes: Optional[int]
    chapters: Optional[int]; score: Optional[int]; url: Optional[str]

class Details(TypedDict):
    source: str; id: int; idMal: Optional[int]; titles: Title
    format: Optional[str]; status: Optional[str]; episodes: Optional[int]
    chapters: Optional[int]; genres: List[str]; tags: List[str]
    score: Dict[str, Optional[int]]; synopsis: str; url: Optional[str]
    external: List[Dict[str, str]]; recommendations: List[MediaHit]

# ---------- Helpers ----------
def err_payload(source: str, code: str, message: str):
    return {"schemaVersion": SCHEMA, "error": {"code": code, "message": message, "source": source}}

def _req(method, url, **kw):
    timeout = kw.pop("timeout", DEFAULT_TIMEOUT)
    headers = {"User-Agent": UA, **kw.pop("headers", {})}
    backoff = 0.7
    for attempt in range(3):
        try:
            r = requests.request(method, url, timeout=timeout, headers=headers, **kw)
            if r.status_code in RETRY_CODES:
                raise requests.HTTPError(f"{r.status_code} upstream", response=r)
            return r
        except requests.HTTPError as e:
            if getattr(e, "response", None) and e.response.status_code in RETRY_CODES and attempt < 2:
                time.sleep(backoff + random.random()*0.4); backoff *= 2
                continue
            raise
        except requests.RequestException:
            if attempt < 2:
                time.sleep(backoff + random.random()*0.4); backoff *= 2
                continue
            raise

def http_get(url, **kw):  return _req("GET", url, **kw)
def http_post(url, **kw): return _req("POST", url, **kw)


def gql(query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
    r = http_post(ANILIST_GQL, json={"query": query, "variables": variables},
                  headers={"Content-Type": "application/json"})
    data = r.json()
    if "errors" in data:
        raise RuntimeError(json.dumps(data["errors"], ensure_ascii=False))
    return data["data"]

def norm_title(t: Dict[str, Any]) -> Title:
    return {"romaji": t.get("romaji"), "english": t.get("english"), "native": t.get("native")}

def norm_hit_from_anilist(m: Dict[str, Any]) -> MediaHit:
    return {
        "source":"anilist", "id":m.get("id"), "idMal":m.get("idMal"),
        "titles": norm_title(m.get("title", {})),
        "year": m.get("seasonYear") or (m.get("startDate", {}) or {}).get("year"),
        "format": m.get("format"), "episodes": m.get("episodes"),
        "chapters": m.get("chapters"), "score": m.get("averageScore"),
        "url": m.get("siteUrl"),
    }

def norm_details_from_anilist(m: Dict[str, Any]) -> Details:
    recs: List[MediaHit] = []
    for node in (m.get("recommendations", {}) or {}).get("nodes", []):
        mr = node.get("mediaRecommendation") or {}
        if mr: recs.append(norm_hit_from_anilist(mr))
    externals = [{"site": ex.get("site") or ex.get("type") or "", "url": ex.get("url") or ""} for ex in (m.get("externalLinks") or [])]
    return {
        "source":"anilist","id":m.get("id"),"idMal":m.get("idMal"),
        "titles": norm_title(m.get("title", {})), "format": m.get("format"),
        "status": m.get("status"), "episodes": m.get("episodes"),
        "chapters": m.get("chapters"), "genres": m.get("genres") or [],
        "tags": [t.get("name") for t in (m.get("tags") or [])],
        "score": {"anilist": m.get("averageScore"), "mal": None},
        "synopsis": (m.get("description") or "").replace("<br>", "\n"),
        "url": m.get("siteUrl"), "external": externals, "recommendations": recs,
    }

# ---------- Tools ----------
@mcp.tool()
def search_media(query: str, kind: str = "ANIME", source: str = "anilist", limit: int = 5):
    """Busca ANIME o MANGA. source: 'anilist' (default) o 'jikan' (fallback)."""
    src = source  # para reportar en errores
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
            return {
                "schemaVersion": SCHEMA,
                "query": query,
                "kind": kind,
                "source": "anilist",
                "results": hits[:limit]
            }

        # Fallback: Jikan (MAL) sin key
        import urllib.parse
        base = "https://api.jikan.moe/v4/anime" if kind == "ANIME" else "https://api.jikan.moe/v4/manga"
        url = f"{base}?q={urllib.parse.quote(query)}&limit={limit}"
        r = http_get(url, headers={"User-Agent": UA})
        payload = r.json()
        out: List[MediaHit] = []
        for it in payload.get("data", []):
            titles = {"romaji": it.get("title"), "english": it.get("title_english"), "native": None}
            out.append({
                "source": "jikan",
                "id": it.get("mal_id"),
                "idMal": it.get("mal_id"),
                "titles": titles,
                "year": it.get("year"),
                "format": (it.get("type") or "").upper(),
                "episodes": it.get("episodes") if kind == "ANIME" else None,
                "chapters": it.get("chapters") if kind == "MANGA" else None,
                "score": int(it.get("score")*10) if it.get("score") else None,
                "url": it.get("url")
            })
        return {
            "schemaVersion": SCHEMA,
            "query": query,
            "kind": kind,
            "source": "jikan",
            "results": out
        }

    except requests.Timeout:
        return err_payload(src, "TIMEOUT", "Upstream timed out")
    except requests.HTTPError as e:
        sc = getattr(e, "response", None).status_code if getattr(e, "response", None) else 0
        return err_payload(src, f"UPSTREAM_{sc}", str(e))
    except Exception as e:
        return err_payload(src, "UNEXPECTED", str(e))


@mcp.tool()
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
            det["schemaVersion"] = SCHEMA
            return det

        base = "https://api.jikan.moe/v4/anime/" if kind == "ANIME" else "https://api.jikan.moe/v4/manga/"
        r = http_get(base + str(id), headers={"User-Agent": UA})
        r.raise_for_status()
        d = r.json().get("data", {})
        titles = {"romaji": d.get("title"), "english": d.get("title_english"), "native": None}
        genres = [g.get("name") for g in d.get("genres", [])]
        score10 = d.get("score")
        return {
            "schemaVersion": SCHEMA,
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
            "score": {"anilist": None, "mal": int(score10*10) if score10 else None},
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


@mcp.tool()
def trending(kind: str = "ANIME", limit: int = 10):
    """Top trending (AniList)."""
    src = "anilist"
    try:
        kind = kind.upper()
        limit = min(max(limit, 1), 25)
        q = """
        query ($type: MediaType, $per: Int){
          Page(perPage: $per){
            media(type:$type, sort: TRENDING_DESC){
              id idMal siteUrl format episodes chapters averageScore seasonYear
              title { romaji english native }
            }
          }
        }"""
        data = gql(q, {"type": kind, "per": limit})
        hits = [norm_hit_from_anilist(m) for m in data["Page"]["media"]]
        return {"schemaVersion": SCHEMA, "kind": kind, "results": hits[:limit]}
    except requests.Timeout:
        return err_payload(src, "TIMEOUT", "Upstream timed out")
    except requests.HTTPError as e:
        sc = getattr(e, "response", None).status_code if getattr(e, "response", None) else 0
        return err_payload(src, f"UPSTREAM_{sc}", str(e))
    except Exception as e:
        return err_payload(src, "UNEXPECTED", str(e))


@mcp.tool()
def health():
    return {"schemaVersion": SCHEMA, "ok": True, "sources": ["anilist", "jikan"]}

@mcp.tool()
def about():
    return {
      "schemaVersion": SCHEMA,
      "name": "anime-helper",
      "version": __VERSION__,
      "endpoints": {"anilist": ANILIST_GQL, "jikan": "https://api.jikan.moe/v4"},
      "limits": {"maxPerPage": 25, "timeoutSec": DEFAULT_TIMEOUT}
    }


if __name__ == "__main__":
    mcp.run()
