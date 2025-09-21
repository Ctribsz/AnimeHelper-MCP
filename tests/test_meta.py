from anime_helper.tools import meta


def test_health_ok():
    h = meta.health()
    assert isinstance(h, dict)
    assert h.get("schemaVersion") == "1.0.0"
    assert h.get("ok") is True
    assert set(h.get("sources", [])) >= {"anilist", "jikan"}
