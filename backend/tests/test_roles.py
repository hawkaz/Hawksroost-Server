from .conftest import login


def test_viewer_can_read_not_write(client):
    login(client, "viewer")
    assert client.get("/api/lists/shopping").status_code == 200
    assert client.post("/api/lists/shopping", json={"text": "Eggs"}).status_code == 403
    assert client.post("/api/calendar", json={"title": "Trip", "start_date": "2026-07-01", "end_date": "2026-07-03"}).status_code == 403
    assert client.post("/api/cameras/1/ptz", json={"command": "Left"}).status_code == 403
    assert client.get("/api/admin/settings").status_code == 403


def test_member_cannot_admin(client):
    login(client, "member")
    assert client.post("/api/lists/shopping", json={"text": "Eggs"}).status_code == 201
    assert client.get("/api/admin/users").status_code == 403
    assert client.put("/api/cameras/1/autotrack", json={"enabled": True}).status_code == 403
    assert client.post("/api/cameras/1/siren", json={"on": True}).status_code == 403   # siren is admin-only
    # The light is a member control: allowed past the role check (camera 1 isn't connected → 503).
    assert client.post("/api/cameras/1/light", json={"on": True}).status_code == 503


def test_settings_secrets_write_only(client):
    login(client, "admin")
    r = client.put("/api/admin/settings/email", json={"enabled": True, "username": "me", "password": "s3cret", "from_email": "cabin@example.com"})
    assert r.status_code == 200
    body = r.json()
    assert "password" not in body and body["password_set"] is True
    # Sending None keeps the secret.
    body = client.put("/api/admin/settings/email", json={"password": None}).json()
    assert body["password_set"] is True
    all_settings = client.get("/api/admin/settings").json()
    assert "push" not in all_settings
    assert all_settings["google"]["redirect_uri"].endswith("/api/auth/google/callback")


def test_login_photo_upload(client):
    login(client, "admin")
    assert client.get("/api/auth/config").json()["login_photo"] is None
    jpg = b"\xff\xd8\xff\xe0" + b"0" * 100
    r = client.put("/api/admin/login-photo", content=jpg, headers={"Content-Type": "image/jpeg"})
    assert r.status_code == 200
    url = client.get("/api/auth/config").json()["login_photo"]
    client.post("/api/auth/logout")
    got = client.get(url)
    assert got.status_code == 200 and got.content == jpg


def test_login_photo_rejects_non_images(client):
    login(client, "admin")
    r = client.put("/api/admin/login-photo", content=b"<svg>", headers={"Content-Type": "image/svg+xml"})
    assert r.status_code == 400
