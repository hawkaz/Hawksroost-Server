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
    r = client.put("/api/admin/settings/email", json={"api_key": "xkeysib-s3cret", "from_email": "cabin@example.com"})
    assert r.status_code == 200
    body = r.json()
    assert "api_key" not in body and body["api_key_set"] is True and "s3cret" not in r.text
    # Sending None keeps the secret.
    body = client.put("/api/admin/settings/email", json={"api_key": None}).json()
    assert body["api_key_set"] is True
    all_settings = client.get("/api/admin/settings").json()
    assert "push" not in all_settings
    assert all_settings["google"]["redirect_uri"].endswith("/api/auth/google/callback")


def test_settings_numbers_stay_sensible(client):
    """A cleared or silly number is refused with a plain message, and nothing is saved."""
    from .conftest import login
    login(client, "admin")
    put = lambda body: client.put("/api/admin/settings/backup", json=body)  # noqa: E731
    assert put({"hour": 4, "keep_days": 7}).json()["keep_days"] == 7
    for body, says in (({"keep_days": None}, "needs a whole number"), ({"keep_days": 0}, "from 1 to 365"),
                       ({"hour": 24}, "from 0 to 23"), ({"hour": 2.5}, "whole number"), ({"hour": "soon"}, "whole number")):
        r = put({"hour": 5} | body)
        assert r.status_code == 422 and says in r.json()["detail"], (body, r.text)
    saved = client.get("/api/admin/settings").json()["backup"]
    assert saved["hour"] == 4 and saved["keep_days"] == 7      # nothing half-saved
    assert client.put("/api/admin/settings/radio", json={"join_gap_s": "15"}).json()["join_gap_s"] == 15
    assert client.put("/api/admin/settings/general", json={"units": "furlongs"}).status_code == 422


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


def test_download_names_are_plain():
    from app.web import file_name
    assert file_name("Porch deck", "2026-07-04-180000", ext="jpg") == "Porch_deck-2026-07-04-180000.jpg"
    assert file_name('Mom\'s "cabin" ☀\r\n', "x/y", ext="mp4") == "Mom_s_cabin-x_y.mp4"
    assert file_name("154.4450 MHz", ext="mp3") == "154.4450_MHz.mp3"
    assert file_name("..", ext="mp3") == "file.mp3"


def test_list_sizes_are_checked(client):
    from .conftest import login
    login(client, "viewer")
    assert client.get("/api/radio/recordings?limit=-1").status_code == 422   # SQLite reads -1 as "everything"
    assert client.get("/api/radio/recordings?limit=60").status_code == 200
    assert client.get("/api/cameras/1/events?limit=0").status_code == 422
