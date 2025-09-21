from typing import Optional, List, Dict, Any
from ..core.cache import gql
from ..core.normalizers import norm_hit_from_anilist
from ..core.http_client import err_payload

def _best_by_format(hits: List[Dict[str, Any]], prefer_format: Optional[str]) -> Optional[Dict[str, Any]]:
    pf = (prefer_format or "").upper()
    if pf:
        for h in hits:
            if (h.get("format") or "").upper() == pf:
                return h
    return hits[0] if hits else None

# Helper interno para usar desde ask()
def resolve_title_best(title: str, kind: str = "ANIME", prefer_format: Optional[str] = None) -> Optional[Dict[str, Any]]:
    q = """
    query ($q:String,$type:MediaType,$per:Int){
      Page(perPage:$per){
        media(search:$q, type:$type, sort:[SEARCH_MATCH,POPULARITY_DESC]){
          id idMal siteUrl format episodes chapters averageScore seasonYear
          title { romaji english native }
        }
      }
    }"""
    data = gql(q, {"q": title, "type": kind.upper(), "per": 10})
    hits = [norm_hit_from_anilist(m) for m in data["Page"]["media"]]
    return _best_by_format(hits, prefer_format)

# Tool MCP (útil para hosts o debugging)
def resolve_title(title: str, kind: str = "ANIME", prefer_format: Optional[str] = None):
    try:
        best = resolve_title_best(title, kind, prefer_format)
        if not best:
            return {"schemaVersion": "1.0.0", "query": title, "kind": kind, "status": "NOT_FOUND"}
        return {"schemaVersion": "1.0.0", "query": title, "kind": kind, "result": best}
    except Exception as e:
        return err_payload("anilist", "UNEXPECTED", str(e))

def register_tools(mcp):
    mcp.tool()(resolve_title)