from tests.conftest import STRONG_PASSWORD


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_setup_login_logout_flow(client):
    assert client.get("/api/auth/state").json() == {"authenticated": False, "setup_required": True,
                                                     "username": None, "csrf_token": None}
    weak = client.post("/api/auth/setup", json={"username": "owner", "password": "short"})
    assert weak.status_code == 422
    r = client.post("/api/auth/setup", json={"username": "owner", "password": STRONG_PASSWORD})
    assert r.status_code == 200
    assert "sp_session" in r.cookies
    assert client.post("/api/auth/setup", json={"username": "x2x", "password": STRONG_PASSWORD}).status_code == 409
    csrf = r.json()["csrf_token"]
    # logout requires CSRF header
    assert client.post("/api/auth/logout").status_code == 403
    assert client.post("/api/auth/logout", headers={"x-csrf-token": csrf}).status_code == 200
    assert client.get("/api/streams").status_code == 401
    bad = client.post("/api/auth/login", json={"username": "owner", "password": "wrong-password"})
    assert bad.status_code == 401
    good = client.post("/api/auth/login", json={"username": "owner", "password": STRONG_PASSWORD})
    assert good.status_code == 200 and good.json()["authenticated"]


def test_mutations_require_csrf(auth_client):
    token = auth_client.headers.pop("x-csrf-token")
    assert auth_client.post("/api/creators", json={"name": "A"}).status_code == 403
    assert auth_client.post("/api/creators", json={"name": "A"}, headers={"x-csrf-token": token}).status_code == 201


def test_login_rate_limit(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "login_rate_limit_per_minute", 3)
    codes = [client.post("/api/auth/login", json={"username": "nobody", "password": "x"}).status_code for _ in range(5)]
    assert codes[:3] == [401, 401, 401]
    assert codes[3:] == [429, 429]


def test_non_local_clients_blocked():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app, client=("8.8.8.8", 5000)) as c:
        assert c.get("/api/health").status_code == 403


def test_settings_roundtrip_and_secret_handling(auth_client, db):
    s = auth_client.get("/api/settings").json()
    assert s["detection"]["weights"] == {"chat": 0.3, "audio": 0.25, "visual": 0.2, "emoji": 0.15, "unique_users": 0.1}
    assert s["clips"]["pre_event_seconds"] == 45 and s["clips"]["post_event_seconds"] == 35
    r = auth_client.put("/api/settings", json={"ai": {"api_key": "secret-gemini-key"}, "clips": {"pre_event_seconds": 30}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ai"]["api_key_configured"] is True
    assert "secret-gemini-key" not in r.text
    assert body["clips"]["pre_event_seconds"] == 30 and body["clips"]["post_event_seconds"] == 35
    from app.models import ApplicationSetting

    stored = db.get(ApplicationSetting, "ai").value["api_key_encrypted"]
    assert stored and "secret-gemini-key" not in stored
    from app.services.app_settings import gemini_api_key, load_settings

    assert gemini_api_key(load_settings(db)) == "secret-gemini-key"
    assert auth_client.put("/api/settings", json={"subtitles": {"primary_color": "red"}}).status_code == 422
    assert auth_client.put("/api/settings", json={"nonsense": {}}).status_code == 422
    assert auth_client.put("/api/settings", json={"clips": {"vertical_mode": "bad"}}).status_code == 422


def test_creator_authorisation_requires_notes(auth_client):
    r = auth_client.post("/api/creators", json={"name": "Creator", "authorised": True})
    assert r.status_code == 422
    r = auth_client.post("/api/creators", json={"name": "Creator", "authorised": True,
                                                "authorisation_notes": "Signed agreement 2026-11-01",
                                                "youtube_channel_id": "UC" + "a" * 22, "preferred_language": "sq"})
    assert r.status_code == 201
    cid = r.json()["id"]
    assert auth_client.get("/api/creators").json()[0]["preferred_language"] == "sq"
    assert auth_client.post("/api/creators", json={"name": "Dup", "youtube_channel_id": "UC" + "a" * 22}).status_code == 409
    assert auth_client.delete(f"/api/creators/{cid}").status_code == 204
