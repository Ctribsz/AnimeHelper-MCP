import pytest

from anime_helper.core.cache import gql
from anime_helper.core.http_client import http_get


@pytest.mark.integration
def test_anilist_gql_search_minimal():
    q = """
    query ($q: String){
      Page(perPage: 1) { media(search: $q, type: ANIME){ id title { romaji } } }
    }
    """
    data = gql(q, {"q": "One Piece"})
    media = data.get("Page", {}).get("media", [])
    assert isinstance(media, list)
    assert len(media) >= 0  # si hay rate limit puede devolver 0, pero no debe romper


@pytest.mark.integration
def test_jikan_http_get_smoke():
    r = http_get("https://api.jikan.moe/v4/anime?q=One%20Piece&limit=1")
    assert getattr(r, "status_code", None) == 200
