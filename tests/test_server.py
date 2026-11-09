import json
import threading
import urllib.error
import urllib.request

import pytest

from aiimagecheck import server

from conftest import MADE


@pytest.fixture
def base_url():
    srv = server.make_server("127.0.0.1:0")
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def post(url, body, headers=None):
    req = urllib.request.Request(url, data=body, method="POST", headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as err:
        body = err.read()
        is_json = err.headers.get("Content-Type") == "application/json"
        return err.code, json.loads(body) if is_json else body.decode()


def test_page_is_served_with_a_strict_policy(base_url):
    with urllib.request.urlopen(base_url + "/", timeout=10) as resp:
        body = resp.read().decode()
        assert resp.status == 200 and "AI Image Check" in body
        assert "default-src 'none'" in resp.headers["Content-Security-Policy"]


def test_check_returns_the_report_and_the_original(base_url):
    status, r = post(base_url + "/check", (MADE / "ai-edited.jpg").read_bytes(), {"X-Filename": "photo.jpg"})
    assert status == 200 and r["verdict"] == "ai_edited" and r["name"] == "photo.jpg"
    assert r["credentials"]["ingredients"][0]["thumbnail"].startswith("data:image/")


def test_empty_and_oversized_uploads_are_refused(base_url, monkeypatch):
    assert post(base_url + "/check", b"")[0] == 413
    monkeypatch.setattr(server, "MAX_UPLOAD", 10)
    assert post(base_url + "/check", b"x" * 11)[0] == 413


def test_unknown_paths_are_404(base_url):
    assert post(base_url + "/elsewhere", b"x")[0] == 404
    with pytest.raises(urllib.error.HTTPError) as err:
        urllib.request.urlopen(base_url + "/etc/passwd", timeout=10)
    assert err.value.code == 404


@pytest.mark.parametrize("listen, ok", [
    ("127.0.0.1:0", True), ("localhost:0", True), ("[::1]:0", True),
    ("0.0.0.0:0", False), (":3103", False), ("192.168.8.190:3103", False), ("127.0.0.1", False),
])
def test_loopback_only(listen, ok):
    if ok:
        srv = server.make_server(listen)
        srv.server_close()
    else:
        with pytest.raises(ValueError):
            server.make_server(listen)
