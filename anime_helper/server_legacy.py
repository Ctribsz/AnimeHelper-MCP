# SPDX-License-Identifier: MIT
from __future__ import annotations

import json, re, random, time, hashlib
from datetime import datetime, timezone
from importlib.metadata import version, PackageNotFoundError
from typing import TypedDict, Optional, List, Dict, Any

import requests
from mcp.server.fastmcp import FastMCP

# ---------- Identidad ----------
mcp = FastMCP("anime-helper")
ANILIST_GQL = "https://graphql.anilist.co"
UA = "anime-helper-mcp/0.1"

try:
    __VERSION__ = version("anime-helper")   # nombre del paquete en pyproject
except PackageNotFoundError:
    __VERSION__ = "0.0.0+dev"

# ---------- Contrato y red ----------
SCHEMA = "1.0.0"
DEFAULT_TIMEOUT = 15
RETRY_CODES = {429, 500, 502, 503, 504}

def _req(method: str, url: str, **kw) -> requests.Response:
    timeout = kw.pop("timeout", DEFAULT_TIMEOUT)
    headers = {"User-Agent": UA, **kw.pop("headers", {})}
    backoff = 0.7
    for attempt in range(3):
        try:
            r = requests.request(method, url, timeout=timeout, headers=headers, **kw)
            # reintentos para 429/5xx
            if r.status_code in RETRY_CODES:
                raise requests.HTTPError(f"{r.status_code} upstream", response=r)
            return r
        except requests.HTTPError as e:
            if getattr(e, "response", None) and e.response.status_code in RETRY_CODES and attempt < 2:
                time.sleep(backoff + random.random() * 0.4)
                backoff *= 2
                continue
            raise
        except requests.RequestException:
            if attempt < 2:
                time.sleep(backoff + random.random() * 0.4)
                backoff *= 2
                continue
            raise

def http_get(url: str, **kw) -> requests.Response:  return _req("GET", url, **kw)
def http_post(url: str, **kw) -> requests.Response: return _req("POST", url, **kw)

def err_payload(source: str, code: str, message: str):
    return {"schemaVersion": SCHEMA, "error": {"code": code, "message": message, "source": source}}

# ---------- Cache GQL (simple en memoria con TTL) ----------
CACHE_TTL = 300  # 5 min
_CACHE: Dict[str, tuple[float, dict]] = {}
_CACHE_HITS = 0
_CACHE_MISSES = 0

def _cache_key_gql(query: str, variables: dict) -> str:
    hq = hashlib.sha1(query.encode("utf-8")).hexdigest()
    hv = hashlib.sha1(json.dumps(variables, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return f"GQL|{hq}|{hv}"

def _cache_get(k: str):
    global _CACHE_HITS, _CACHE_MISSES
    now = time.time()
    it = _CACHE.get(k)
    if not it:
        _CACHE_MISSES += 1
        return None
    exp, data = it
    if exp < now:
        _CACHE.pop(k, None)
        _CACHE_MISSES += 1
        return None
    _CACHE_HITS += 1
    return data

def _cache_set(k: str, data: dict, ttl: int = CACHE_TTL):
    _CACHE[k] = (time.time() + ttl, data)

def gql(query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
    k = _cache_key_gql(query, variables)
    cached = _cache_get(k)
    if cached is not None:
        return cached
    r = http_post(ANILIST_GQL, json={"query": query, "variables": variables},
                  headers={"Content-Type": "application/json"})
    data = r.json()
    if "errors" in data:
        raise RuntimeError(json.dumps(data["errors"], ensure_ascii=False))
    out = data["data"]
    _cache_set(k, out)
    return out

# ---------- Tipos ----------
class Title(TypedDict):
    romaji: Optional[str]
    english: Optional[str]
    native: Optional[str]

class MediaHit(TypedDict):
    source: str
    id: int
    idMal: Optional[int]
    titles: Title
    year: Optional[int]
    format: Optional[str]          # TV/MOVIE/OVA/ONA/MANGA/ONE_SHOT...
    episodes: Optional[int]
    chapters: Optional[int]
    score: Optional[int]           # 0-100
    url: Optional[str]

class Details(TypedDict):
    source: str
    id: int
    idMal: Optional[int]
    titles: Title
    format: Optional[str]
    status: Optional[str]
    episodes: Optional[int]
    chapters: Optional[int]
    genres: List[str]
    tags: List[str]
    score: Dict[str, Optional[int]]   # {"anilist": 86, "mal": 84}
    synopsis: str
    url: Optional[str]
    external: List[Dict[str, str]]
    recommendations: List[MediaHit]

class AiringItem(TypedDict):
    when: int
    episode: int
    media: MediaHit

# ---------- Normalizadores ----------
def norm_title(t: Dict[str, Any]) -> Title:
    return {"romaji": t.get("romaji"), "english": t.get("english"), "native": t.get("native")}

def norm_hit_from_anilist(m: Dict[str, Any]) -> MediaHit:
    return {
        "source": "anilist",
        "id": m.get("id"),
        "idMal": m.get("idMal"),
        "titles": norm_title(m.get("title", {})),
        "year": m.get("seasonYear") or (m.get("startDate", {}) or {}).get("year"),
        "format": m.get("format"),
        "episodes": m.get("episodes"),
        "chapters": m.get("chapters"),
        "score": m.get("averageScore"),
        "url": m.get("siteUrl"),
    }

def norm_details_from_anilist(m: Dict[str, Any]) -> Details:
    recs: List[MediaHit] = []
    for node in (m.get("recommendations", {}) or {}).get("nodes", []):
        mr = node.get("mediaRecommendation") or {}
        if mr:
            recs.append(norm_hit_from_anilist(mr))
    externals = [{"site": ex.get("site") or ex.get("type") or "", "url": ex.get("url") or ""} for ex in (m.get("externalLinks") or [])]
    return {
        "source": "anilist",
        "id": m.get("id"),
        "idMal": m.get("idMal"),
        "titles": norm_title(m.get("title", {})),
        "format": m.get("format"),
        "status": m.get("status"),
        "episodes": m.get("episodes"),
        "chapters": m.get("chapters"),
        "genres": m.get("genres") or [],
        "tags": [t.get("name") for t in (m.get("tags") or [])],
        "score": {"anilist": m.get("averageScore"), "mal": None},
        "synopsis": (m.get("description") or "").replace("<br>", "\n"),
        "url": m.get("siteUrl"),
        "external": externals,
        "recommendations": recs,
    }

# ---------- Helpers de temporada ----------
def _season_from_month(m: int) -> str:
    if m in (12, 1, 2):  return "WINTER"
    if m in (3, 4, 5):   return "SPRING"
    if m in (6, 7, 8):   return "SUMMER"
    return "FALL"

# ---------- Tools de cache ----------
@mcp.tool()
def cache_info():
    """Estadísticas simples del cache GQL."""
    return {"schemaVersion": SCHEMA, "hits": _CACHE_HITS, "misses": _CACHE_MISSES, "size": len(_CACHE), "ttlSec": CACHE_TTL}

@mcp.tool()
def cache_clear():
    """Limpia el cache GQL."""
    n = len(_CACHE)
    _CACHE.clear()
    return {"schemaVersion": SCHEMA, "cleared": n}

# ---------- Tools principales ----------
@mcp.tool()
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
            return {"schemaVersion": SCHEMA, "query": query, "kind": kind, "source": "anilist", "results": hits[:limit]}

        # Fallback Jikan (MAL) sin key
        import urllib.parse
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
        return {"schemaVersion": SCHEMA, "query": query, "kind": kind, "source": "jikan", "results": out}

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
        r = http_get(base + str(id))
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

@mcp.tool()
def trending(kind: str = "ANIME", limit: int = 10, format_in: Optional[List[str]] = None):
    """Top trending (AniList). Opcional: format_in=['MOVIE','TV','OVA','ONA','SPECIAL']"""
    src = "anilist"
    try:
        kind = kind.upper()
        limit = min(max(limit, 1), 25)
        formats = [f.upper() for f in (format_in or [])] or None
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
        return {"schemaVersion": SCHEMA, "kind": kind, "format_in": formats, "results": hits[:limit]}
    except requests.Timeout:
        return err_payload(src, "TIMEOUT", "Upstream timed out")
    except requests.HTTPError as e:
        sc = getattr(e, "response", None).status_code if getattr(e, "response", None) else 0
        return err_payload(src, f"UPSTREAM_{sc}", str(e))
    except Exception as e:
        return err_payload(src, "UNEXPECTED", str(e))

@mcp.tool()
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
        sea = (season or _season_from_month(now.month)).upper()
        yr = int(year or now.year)
        formats = [f.upper() for f in (format_in or [])] or None

        if kind == "ANIME":
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
            return {"schemaVersion": SCHEMA, "kind": "ANIME", "season": sea, "year": yr, "sort": sort, "format_in": formats, "results": hits[:limit]}

        # Para MANGA no hay season en AniList; usamos trending como proxy
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
        return {"schemaVersion": SCHEMA, "kind": "MANGA", "season": None, "year": None, "sort": "TRENDING_DESC", "results": hits[:limit]}
    except requests.Timeout:
        return err_payload("anilist", "TIMEOUT", "Upstream timed out")
    except requests.HTTPError as e:
        sc = getattr(e, "response", None).status_code if getattr(e, "response", None) else 0
        return err_payload("anilist", f"UPSTREAM_{sc}", str(e))
    except Exception as e:
        return err_payload("anilist", "UNEXPECTED", str(e))

@mcp.tool()
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
                return {"schemaVersion": SCHEMA, "query": query, "status": "NOT_FOUND"}
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
            "schemaVersion": SCHEMA,
            "id": m["id"],
            "titles": {"romaji": (m["title"] or {}).get("romaji"),
                       "english": (m["title"] or {}).get("english"),
                       "native": (m["title"] or {}).get("native")},
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

@mcp.tool()
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
        return {"schemaVersion": SCHEMA, "days": days, "results": items}
    except requests.Timeout:
        return err_payload("anilist", "TIMEOUT", "Upstream timed out")
    except requests.HTTPError as e:
        sc = getattr(e, "response", None).status_code if getattr(e, "response", None) else 0
        return err_payload("anilist", f"UPSTREAM_{sc}", str(e))
    except Exception as e:
        return err_payload("anilist", "UNEXPECTED", str(e))

@mcp.tool()
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
        return {"schemaVersion": SCHEMA, "title": title, "kind": kind, "best": best, "candidates": hits}
    except Exception as e:
        return err_payload("anilist", "UNEXPECTED", str(e))

# ---------- Router de lenguaje natural ----------
def _parse_kind(text: str, default: str = "ANIME") -> str:
    t = text.lower()
    if "manga" in t: return "MANGA"
    if "anime" in t: return "ANIME"
    return default.upper()

def _parse_limit(text: str, default: int = 5) -> int:
    m = re.search(r"\b(\d{1,2})\b", text)
    if m:
        try:
            n = int(m.group(1))
            return max(1, min(25, n))
        except ValueError:
            pass
    return default

def _strip_keywords(text: str, *words: str) -> str:
    t = text
    for w in words:
        t = re.sub(re.escape(w), " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\s+", " ", t).strip(" ?!.,")
    return t

@mcp.tool()
def ask(text: str, default_kind: str = "ANIME", default_limit: int = 5):
    """
    Lenguaje natural (ES/EN). Detecta intención y usa internamente:
    - airing_status (¿en qué capítulo va...?)
    - season_top (esta temporada; soporta 'películas')
    - trending (tendencias / populares; soporta 'películas')
    - search_media (+ media_details si piden ficha/detalles o 'qué es')
    - media_details para '¿cuántos episodios/capítulos tiene X?'
    Devuelve: {schemaVersion, intent, args, result}
    """
    try:
        if not text or not text.strip():
            return err_payload("router", "BAD_REQUEST", "Empty text")

        low = text.lower()
        kind = _parse_kind(low, default_kind)
        limit = _parse_limit(low, default_limit)
        wants_movies = any(w in low for w in ["película", "peliculas", "película", "movie", "movies", "film", "films"])

        # 1) ¿En qué capítulo/episodio va ...?
        if re.search(r"(en\s+qué|en que).*(cap[ií]tulo|episodio)", low) or \
           re.search(r"(cap[ií]tulo|episodio).*(va|actual|último|ultimo)", low):
            title = _strip_keywords(text, "en qué", "en que", "capitulo", "capítulo", "episodio",
                                    "va", "actual", "último", "ultimo", "de", "del", "la", "el")
            title = title or text
            res = airing_status(query=title)
            return {"schemaVersion": SCHEMA, "intent": "airing_status", "args": {"query": title}, "result": res}

        # 2) Cuántos episodios/capítulos tiene X
        if re.search(r"(cu[aá]nt[oa]s?|cuantos|cuantas).*(episodios|cap[ií]tulos|capitulos)", low):
            title = _strip_keywords(text, "cuantos", "cuantas", "cuánto", "cuanta", "episodios", "capitulos", "capítulos",
                                    "tiene", "de", "del", "la", "el") or text
            s = search_media(query=title, kind=kind, limit=3)
            best = None
            for hit in s.get("results", []):
                if hit.get("source") == "anilist":
                    best = hit; break
                if best is None: best = hit
            if not best:
                return {"schemaVersion": SCHEMA, "intent": "count", "args": {"query": title, "kind": kind}, "result": s}
            if best["source"] == "anilist":
                det = media_details(source="anilist", id=best["id"], kind=kind)
            else:
                det = media_details(source="jikan", id=best.get("idMal") or best["id"], kind=kind)
            return {"schemaVersion": SCHEMA, "intent": "count", "args": {"query": title, "kind": kind}, "result": det}

        # 3) “qué es / de qué trata X” → ficha
        if any(w in low for w in ["qué es", "que es", "de qué trata", "de que trata", "what is"]):
            title = _strip_keywords(text, "qué es", "que es", "de qué trata", "de que trata", "what is", "de", "del", "la", "el") or text
            s = search_media(query=title, kind=kind, limit=3)
            best = None
            for hit in s.get("results", []):
                if hit.get("source") == "anilist":
                    best = hit; break
                if best is None: best = hit
            if not best:
                return {"schemaVersion": SCHEMA, "intent": "what_is", "args": {"query": title, "kind": kind}, "result": s}
            if best["source"] == "anilist":
                det = media_details(source="anilist", id=best["id"], kind=kind)
            else:
                det = media_details(source="jikan", id=best.get("idMal") or best["id"], kind=kind)
            return {"schemaVersion": SCHEMA, "intent": "what_is", "args": {"query": title, "kind": kind}, "result": det}

        # 4) Temporada actual / esta temporada (ANIME), con opción películas
        if ("temporada" in low and ("actual" in low or "esta" in low)) or re.search(r"\b(this|current)\s+season\b", low):
            formats = ["MOVIE"] if wants_movies else None
            res = season_top(kind="ANIME", limit=limit, format_in=formats)
            return {"schemaVersion": SCHEMA, "intent": "season_top", "args": {"kind": "ANIME", "limit": limit, "format_in": formats}, "result": res}

        # 5) Tendencias / populares / llamativos (con opción películas)
        if any(w in low for w in ["tendencia", "tendencias", "trending", "populares", "más llamativos", "mas llamativos"]):
            formats = ["MOVIE"] if wants_movies else None
            res = trending(kind=kind, limit=limit, format_in=formats)
            return {"schemaVersion": SCHEMA, "intent": "trending", "args": {"kind": kind, "limit": limit, "format_in": formats}, "result": res}

        # 6) Detalles / ficha de X
        if any(w in low for w in ["detalles", "detalle", "ficha", "info de", "información de", "informacion de", "about"]):
            title = _strip_keywords(text, "detalles", "detalle", "ficha", "info de",
                                    "información de", "informacion de", "about", "de", "del", "la", "el") or text
            s = search_media(query=title, kind=kind, limit=3)
            best = None
            for hit in s.get("results", []):
                if hit.get("source") == "anilist":
                    best = hit; break
                if best is None: best = hit
            if not best:
                return {"schemaVersion": SCHEMA, "intent": "search_then_details", "args": {"query": title}, "result": s}
            if best["source"] == "anilist":
                det = media_details(source="anilist", id=best["id"], kind=kind)
            else:
                det = media_details(source="jikan", id=best.get("idMal") or best["id"], kind=kind)
            return {"schemaVersion": SCHEMA, "intent": "search_then_details", "args": {"query": title, "kind": kind}, "result": det}

        # 7) Por defecto: búsqueda
        s = search_media(query=text, kind=kind, limit=limit)
        return {"schemaVersion": SCHEMA, "intent": "search", "args": {"query": text, "kind": kind, "limit": limit}, "result": s}

    except requests.Timeout:
        return err_payload("router", "TIMEOUT", "Upstream timed out")
    except requests.HTTPError as e:
        sc = getattr(e, "response", None).status_code if getattr(e, "response", None) else 0
        return err_payload("router", f"UPSTREAM_{sc}", str(e))
    except Exception as e:
        return err_payload("router", "UNEXPECTED", str(e))

# ---------- Salud, ayuda y metadatos ----------
@mcp.tool()
def health():
    return {"schemaVersion": SCHEMA, "ok": True, "sources": ["anilist", "jikan"]}

@mcp.tool()
def help():
    """
    Casos de uso y ejemplos de invocación (para hosts y usuarios).
    """
    return {
        "schemaVersion": SCHEMA,
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

@mcp.tool()
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

@mcp.tool()
def about():
    return {
        "schemaVersion": SCHEMA,
        "name": "anime-helper",
        "version": __VERSION__,
        "endpoints": {"anilist": ANILIST_GQL, "jikan": "https://api.jikan.moe/v4"},
        "limits": {"maxPerPage": 25, "timeoutSec": DEFAULT_TIMEOUT}
    }

# ---------- Main ----------
if __name__ == "__main__":
    mcp.run()