"""Type definitions for AnimeHelper-MCP."""

from typing import TypedDict, Optional, List, Dict


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