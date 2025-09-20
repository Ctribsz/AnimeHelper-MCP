"""Cache system for GraphQL queries."""

import json
import time
import hashlib
from typing import Dict, Any, Optional, Tuple

from .http_client import http_post

# Constants
CACHE_TTL = 300  # 5 min
ANILIST_GQL = "https://graphql.anilist.co"

# Cache storage
_CACHE: Dict[str, Tuple[float, dict]] = {}
_CACHE_HITS = 0
_CACHE_MISSES = 0


def _cache_key_gql(query: str, variables: dict) -> str:
    """Generate a cache key for GraphQL queries."""
    hq = hashlib.sha1(query.encode("utf-8")).hexdigest()
    hv = hashlib.sha1(json.dumps(variables, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return f"GQL|{hq}|{hv}"


def _cache_get(k: str) -> Optional[dict]:
    """Get item from cache if not expired."""
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


def _cache_set(k: str, data: dict, ttl: int = CACHE_TTL) -> None:
    """Set item in cache with TTL."""
    _CACHE[k] = (time.time() + ttl, data)


def gql(query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
    """Execute GraphQL query with caching."""
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


def cache_info() -> Dict[str, Any]:
    """Get cache statistics."""
    return {
        "hits": _CACHE_HITS,
        "misses": _CACHE_MISSES,
        "size": len(_CACHE),
        "ttlSec": CACHE_TTL
    }


def cache_clear() -> int:
    """Clear cache and return number of cleared items."""
    n = len(_CACHE)
    _CACHE.clear()
    return n
