import pytest
import types

from anime_helper.core import http_client as hc


class DummyResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json = json_data or {}

    def json(self):
        return self._json


def test_http_get_success(monkeypatch):
    calls = {"n": 0}

    def fake_request(method, url, timeout=None, headers=None, **kw):
        calls["n"] += 1
        assert method == "GET"
        assert url == "https://example.com"
        return DummyResponse(200, {"ok": True})

    monkeypatch.setattr(hc.requests, "request", fake_request)

    r = hc.http_get("https://example.com")
    assert isinstance(r, DummyResponse)
    assert r.json()["ok"] is True
    assert calls["n"] == 1, "No debe reintentar en 200"


def test_http_retry_on_5xx_then_success(monkeypatch):
    calls = {"n": 0}

    def fake_request(method, url, timeout=None, headers=None, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            # primer intento: 503 provoca retry
            resp = DummyResponse(503, {})
            err = hc.requests.HTTPError("503 upstream")
            err.response = resp
            raise err
        return DummyResponse(200, {"ok": True})

    # no dormir durante backoff
    monkeypatch.setattr(hc, "time", types.SimpleNamespace(sleep=lambda *_: None))
    monkeypatch.setattr(hc.requests, "request", fake_request)

    r = hc.http_get("https://api.service/test")
    assert r.status_code == 200
    assert calls["n"] == 2, "Debe reintentar una vez y luego salir con éxito"


def test_http_retry_then_raise_after_exhausted(monkeypatch):
    calls = {"n": 0}

    def fake_request(method, url, timeout=None, headers=None, **kw):
        calls["n"] += 1
        # siempre devuelve 500 para forzar los 3 intentos
        resp = DummyResponse(500, {})
        err = hc.requests.HTTPError("500 upstream")
        err.response = resp
        raise err

    monkeypatch.setattr(hc, "time", types.SimpleNamespace(sleep=lambda *_: None))
    monkeypatch.setattr(hc.requests, "request", fake_request)

    with pytest.raises(hc.requests.HTTPError):
        hc.http_get("https://bad.example")
    assert calls["n"] == 3, "Debe agotar 3 intentos"


def test_http_request_exception_retry_then_fail(monkeypatch):
    calls = {"n": 0}

    class Boom(hc.requests.RequestException):
        pass

    def fake_request(method, url, timeout=None, headers=None, **kw):
        calls["n"] += 1
        raise Boom("network down")

    monkeypatch.setattr(hc, "time", types.SimpleNamespace(sleep=lambda *_: None))
    monkeypatch.setattr(hc.requests, "request", fake_request)

    with pytest.raises(Boom):
        hc.http_get("https://down.example")
    assert calls["n"] == 3
