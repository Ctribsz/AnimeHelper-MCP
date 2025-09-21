"""HTTP client and network functions for AnimeHelper-MCP."""

import time
import random
import requests
from typing import Dict, Any

# Constants
DEFAULT_TIMEOUT = 15
RETRY_CODES = {429, 500, 502, 503, 504}
UA = "anime-helper-mcp/0.1"
SCHEMA = "1.0.0"


def _req(method: str, url: str, **kw) -> requests.Response:
    """Internal request function with retry logic."""
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


def http_get(url: str, **kw) -> requests.Response:
    return _req("GET", url, **kw)


def http_post(url: str, **kw) -> requests.Response:
    return _req("POST", url, **kw)


def err_payload(source: str, code: str, message: str) -> Dict[str, Any]:
    return {"schemaVersion": SCHEMA, "error": {"code": code, "message": message, "source": source}}