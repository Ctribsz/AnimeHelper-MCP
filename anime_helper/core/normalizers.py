"""Data normalization functions for different API sources."""

from typing import Dict, Any, List
from ..models.types import Title, MediaHit, Details


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