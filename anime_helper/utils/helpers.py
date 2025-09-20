"""Helper functions for AnimeHelper-MCP."""


def season_from_month(m: int) -> str:
    """Get season name from month number."""
    if m in (12, 1, 2):
        return "WINTER"
    if m in (3, 4, 5):
        return "SPRING"
    if m in (6, 7, 8):
        return "SUMMER"
    return "FALL"
