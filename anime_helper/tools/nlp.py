"""Natural language processing tools for AnimeHelper-MCP."""
import re
from typing import Dict, Any
import requests
from ..core.http_client import err_payload
from .search import search_media
from .details import media_details
from .airing import airing_status
from .trending import trending, season_top


def _parse_kind(text: str, default: str = "ANIME") -> str:
    t = text.lower()
    if "manga" in t:
        return "MANGA"
    if "anime" in t:
        return "ANIME"
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


def _extract_title_for_count(text: str) -> str:
    t = text.strip()
    # quita signos iniciales y espacios
    t = re.sub(r"^[¿?\s]+", "", t)
    # patrones típicos: "cuántos episodios/capítulos tiene X", "cuantos ... de X"
    patterns = [
        r"(cu[aá]nt[oa]s?|cuantos|cuantas)\s+(episodios|cap[ií]tulos|capitulos)\s+(tiene|de)\s+",
        r"(tiene|hay)\s+(cu[aá]nt[oa]s?|cuantos|cuantas)\s+(episodios|cap[ií]tulos|capitulos)\s+de\s+",
    ]
    for p in patterns:
        t = re.sub(p, "", t, flags=re.IGNORECASE)
    # limpia cola
    t = re.sub(r"\s*(\?|¿|\.|!|,|;|:)+\s*$", "", t)
    return t.strip()

def _strip_keywords(text: str, *words: str) -> str:
    t = text
    for w in words:
        t = re.sub(re.escape(w), " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\s+", " ", t).strip(" ?!.,")
    return t


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
        wants_movies = any(w in low for w in ["película", "peliculas", "movie", "movies", "film", "films"])

        # 1) ¿En qué capítulo/episodio va ...?
        if re.search(r"(en\s+qué|en que).*(cap[ií]tulo|episodio)", low) or \
           re.search(r"(cap[ií]tulo|episodio).*(va|actual|último|ultimo)", low):
            title = _strip_keywords(text, "en qué", "en que", "capitulo", "capítulo", "episodio",
                                    "va", "actual", "último", "ultimo", "de", "del", "la", "el") or text
            res = airing_status(query=title)
            return {"schemaVersion": "1.0.0", "intent": "airing_status", "args": {"query": title}, "result": res}

        # 2) Cuántos episodios/capítulos tiene X
        if re.search(r"(cu[aá]nt[oa]s?|cuantos|cuantas).*(episodios|cap[ií]tulos|capitulos)", low):
            title = _extract_title_for_count(text) or text
            # Usa resolve_title para agarrar la serie "canónica"
            prefer = "MANGA" if kind == "MANGA" else "TV"
            try:
                from .resolve import resolve_title_best
                best = resolve_title_best(title, kind=kind, prefer_format=prefer)
            except Exception:
                best = None

            if not best:
                s = search_media(query=title, kind=kind, limit=3)
                return {"schemaVersion": "1.0.0", "intent": "count", "args": {"query": title, "kind": kind}, "result": s}

            det = media_details(
                source="anilist" if best["source"] == "anilist" else "jikan",
                id=best["id"] if best["source"] == "anilist" else (best.get("idMal") or best["id"]),
                kind=kind
            )
    return {"schemaVersion": "1.0.0", "intent": "count", "args": {"query": title, "kind": kind}, "result": det}

        # 3) "qué es / de qué trata X" → ficha
        if any(w in low for w in ["qué es", "que es", "de qué trata", "de que trata", "what is"]):
            title = _strip_keywords(text, "qué es", "que es", "de qué trata", "de que trata", "what is", "de", "del", "la", "el") or text
            s = search_media(query=title, kind=kind, limit=3)
            best = None
            for hit in s.get("results", []):
                if hit.get("source") == "anilist":
                    best = hit; break
                if best is None: best = hit
            if not best:
                return {"schemaVersion": "1.0.0", "intent": "what_is", "args": {"query": title, "kind": kind}, "result": s}
            det = media_details(source="anilist" if best["source"]=="anilist" else "jikan",
                                id=best["id"] if best["source"]=="anilist" else (best.get("idMal") or best["id"]),
                                kind=kind)
            return {"schemaVersion": "1.0.0", "intent": "what_is", "args": {"query": title, "kind": kind}, "result": det}

        # 4) Temporada actual / esta temporada (ANIME), opción películas
        if ("temporada" in low and ("actual" in low or "esta" in low)) or re.search(r"\b(this|current)\s+season\b", low):
            formats = ["MOVIE"] if wants_movies else None
            res = season_top(kind="ANIME", limit=limit, format_in=formats)
            return {"schemaVersion": "1.0.0", "intent": "season_top", "args": {"kind": "ANIME", "limit": limit, "format_in": formats}, "result": res}

        # 5) Tendencias / populares / llamativos (con opción películas)
        if any(w in low for w in ["tendencia", "tendencias", "trending", "populares", "más llamativos", "mas llamativos"]):
            formats = ["MOVIE"] if wants_movies else None
            res = trending(kind=kind, limit=limit, format_in=formats)
            return {"schemaVersion": "1.0.0", "intent": "trending", "args": {"kind": kind, "limit": limit, "format_in": formats}, "result": res}

        # 6) Detalles / ficha de X
        if any(w in low for w in ["detalles", "detalle", "ficha", "info de", "información de", "informacion de", "about"]):
            title = _strip_keywords(text, "detalles", "detalle", "ficha", "info de", "información de", "informacion de", "about", "de", "del", "la", "el") or text
            s = search_media(query=title, kind=kind, limit=3)
            best = None
            for hit in s.get("results", []):
                if hit.get("source") == "anilist":
                    best = hit; break
                if best is None: best = hit
            if not best:
                return {"schemaVersion": "1.0.0", "intent": "search_then_details", "args": {"query": title}, "result": s}
            det = media_details(source="anilist" if best["source"]=="anilist" else "jikan",
                                id=best["id"] if best["source"]=="anilist" else (best.get("idMal") or best["id"]),
                                kind=kind)
            return {"schemaVersion": "1.0.0", "intent": "search_then_details", "args": {"query": title, "kind": kind}, "result": det}

        # 7) Por defecto: búsqueda
        s = search_media(query=text, kind=kind, limit=limit)
        return {"schemaVersion": "1.0.0", "intent": "search", "args": {"query": text, "kind": kind, "limit": limit}, "result": s}

    except requests.Timeout:
        return err_payload("router", "TIMEOUT", "Upstream timed out")
    except requests.HTTPError as e:
        sc = getattr(e, "response", None).status_code if getattr(e, "response", None) else 0
        return err_payload("router", f"UPSTREAM_{sc}", str(e))
    except Exception as e:
        return err_payload("router", "UNEXPECTED", str(e))


def register_tools(mcp):
    mcp.tool()(ask)