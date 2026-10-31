from app.db import SessionLocal
from app.models import Invite
from app.security import hash_token
from app.timeutil import utcnow
from datetime import timedelta

from .conftest import login, make_user


def test_requires_login(client):
    assert client.get("/api/today").status_code == 401
    assert client.get("/api/auth/check").status_code == 401


def test_password_login_and_logout(client):
    make_user("member", "sam@example.com")
    r = client.post("/api/auth/login", json={"email": "SAM@example.com", "password": "correct horse"})
    assert r.status_code == 200
    assert r.json()["role"] == "member"
    assert client.get("/api/auth/check").status_code == 204
    me = client.get("/api/auth/me").json()
    assert me["push_public_key"]  # generated on startup
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401


def test_bad_password(client):
    make_user("member", "sam@example.com")
    r = client.post("/api/auth/login", json={"email": "sam@example.com", "password": "nope"})
    assert r.status_code == 401


def test_invite_flow(client):
    login(client, "admin")
    r = client.post("/api/admin/invites", json={"name": "Pat", "role": "viewer"})
    assert r.status_code == 201
    token = r.json()["url"].rsplit("/", 1)[1]
    client.post("/api/auth/logout")
    assert client.get(f"/api/auth/invite/{token}").json()["role"] == "viewer"
    r = client.post(f"/api/auth/invite/{token}", json={"name": "Pat", "email": "pat@example.com", "password": "long enough pw"})
    assert r.status_code == 200
    assert r.json()["role"] == "viewer"
    # Used once only.
    client.post("/api/auth/logout")
    assert client.get(f"/api/auth/invite/{token}").status_code == 404


def test_expired_invite(client):
    with SessionLocal() as db:
        db.add(Invite(token_hash=hash_token("tok"), role="member", expires_at=utcnow() - timedelta(minutes=1)))
        db.commit()
    assert client.get("/api/auth/invite/tok").status_code == 404


def test_cross_site_write_blocked(client):
    make_user("member", "sam@example.com")
    r = client.post("/api/auth/login", json={"email": "sam@example.com", "password": "correct horse"},
                    headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_last_admin_protected(client):
    login(client, "admin")
    me = client.get("/api/auth/me").json()
    r = client.patch(f"/api/admin/users/{me['id']}", json={"role": "member"})
    assert r.status_code == 400


def test_reset_link(client):
    login(client, "admin")
    uid = make_user("member", "kid@example.com")
    url = client.post(f"/api/admin/users/{uid}/reset-link").json()["url"]
    token = url.rsplit("/", 1)[1]
    client.post("/api/auth/logout")
    assert client.post(f"/api/auth/reset/{token}", json={"password": "brand new pw"}).status_code == 200
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"email": "kid@example.com", "password": "brand new pw"}).status_code == 200
