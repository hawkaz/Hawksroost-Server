"""Camera drivers and admin camera setup. Real cameras can't be reached from tests,
so these cover the generic parts: credentials, event mapping, capabilities, errors."""
import asyncio

from app.db import SessionLocal
from app.models import Camera
from app.routers.cameras import split_credentials
from app.services import cameras as cams
from app.services.cameras.drivers import Driver, NotSupported, onvif_detection, with_credentials

from .conftest import login


def test_credentials_round_trip():
    url = with_credentials("rtsp://10.0.0.5:554/stream1", "cabin", "p@ss:word")
    assert url == "rtsp://cabin:p%40ss%3Aword@10.0.0.5:554/stream1"
    assert split_credentials(url) == ("rtsp://10.0.0.5:554/stream1", "cabin", "p@ss:word")
    # A URL that already has a login is left alone.
    assert with_credentials("rtsp://a:b@h/x", "c", "d") == "rtsp://a:b@h/x"


def test_onvif_topics_map_to_detections():
    assert onvif_detection("tns1:RuleEngine/CellMotionDetector/Motion") == "motion"
    assert onvif_detection("tns1:RuleEngine/MyRuleDetector/PeopleDetect") == "person"
    assert onvif_detection("tns1:RuleEngine/MyRuleDetector/VehicleDetect") == "vehicle"
    assert onvif_detection("tns1:RuleEngine/MyRuleDetector/DogCatDetect") == "animal"
    assert onvif_detection("tns1:VideoSource/ImageTooDark") is None


def test_stream_camera_keeps_login_out_of_the_url(client):
    login(client, "admin")
    r = client.post("/api/admin/cameras", json={
        "name": "Gate", "kind": "stream",
        "options": {"main_url": "rtsp://gate:secret@192.168.67.50/live/main"}})
    assert r.status_code == 201, r.text
    cam = r.json()
    assert cam["options"]["main_url"] == "rtsp://192.168.67.50/live/main"
    assert cam["username"] == "gate" and cam["password_set"] and cam["host"] == "192.168.67.50"
    assert "secret" not in r.text


def test_camera_form_checks_per_kind(client):
    login(client, "admin")
    r = client.post("/api/admin/cameras", json={"name": "Shed", "kind": "onvif", "username": "u", "password": "p"})
    assert r.status_code == 422 and "address" in r.json()["detail"]
    r = client.post("/api/admin/cameras", json={"name": "Gate", "kind": "stream", "options": {"main_url": "ftp://x"}})
    assert r.status_code == 422
    r = client.post("/api/admin/cameras", json={"name": "Deck", "kind": "reolink", "host": "10.0.0.9", "username": "u"})
    assert r.status_code == 400  # needs a password


class FakeDriver(Driver):
    kind = "fake"

    async def connect(self):
        caps = {"ptz": True, "zoom": False, "presets": True, "recordings": False, "events": True,
                "ai_types": ["person"], "siren": False, "light": True}
        return {"model": "Acme 1", "firmware": "1.0", "caps": caps,
                "streams": {"main": "rtsp://h/main", "sub": "rtsp://h/sub"}}

    def presets(self):
        return [{"id": "home", "name": "Home"}]

    async def light(self, on):
        self.lit = on


def test_capabilities_drive_the_api(client, monkeypatch):
    login(client, "admin")
    with SessionLocal() as db:
        cam = Camera(name="Porch", kind="stream", host="h", options={"main_url": "rtsp://h/main"})
        db.add(cam)
        db.commit()
        cam_id = cam.id
    registered = {}

    async def set_stream(name, src):
        registered[name] = src
        return True

    async def remove_stream(name):
        registered.pop(name, None)

    monkeypatch.setattr(cams.go2rtc, "set_stream", set_stream)
    monkeypatch.setattr(cams.go2rtc, "remove_stream", remove_stream)
    driver = FakeDriver(cam_id, "h", None, "", "", 0, {})
    conn = cams.Conn(cam_id=cam_id, driver=driver)
    asyncio.run(cams.manager._connect(conn))
    cams.manager.conns[cam_id] = conn
    try:
        assert set(registered) == {f"cam{cam_id}_main", f"cam{cam_id}_sub"}
        out = next(c for c in client.get("/api/cameras").json() if c["id"] == cam_id)
        assert out["online"] and out["model"] == "Acme 1"
        assert out["ptz"] and out["light"] and not out["siren"] and not out["recordings"]
        assert out["presets"] == [{"id": "home", "name": "Home"}]
        assert set(out["streams"]) == {"main", "sub"}
        # Supported → done; unsupported → a plain 400.
        assert client.post(f"/api/cameras/{cam_id}/light", json={"on": True}).status_code == 204
        assert driver.lit is True
        r = client.post(f"/api/cameras/{cam_id}/siren", json={"on": True})
        assert r.status_code == 400 and "can't" in r.json()["detail"]
        # Bad PTZ command is rejected before it reaches the driver.
        assert client.post(f"/api/cameras/{cam_id}/ptz", json={"command": "Spin"}).status_code == 422
    finally:
        cams.manager.conns.pop(cam_id, None)
    # Offline camera → 503.
    assert client.post(f"/api/cameras/{cam_id}/light", json={"on": True}).status_code == 503


def test_only_new_detections_become_events(monkeypatch):
    started = []

    async def fake_event(conn, kind):
        started.append(kind)

    async def run():
        cams.manager._loop = asyncio.get_running_loop()
        monkeypatch.setattr(cams.manager, "_event", fake_event)
        conn = cams.Conn(cam_id=99, driver=FakeDriver(99, "h", None, "", "", 0, {}))
        cams.manager._on_change(conn, {"motion"})
        cams.manager._on_change(conn, {"motion", "person"})
        cams.manager._on_change(conn, {"person"})
        cams.manager._on_change(conn, set())
        cams.manager._on_change(conn, {"motion"})
        await asyncio.sleep(0)

    asyncio.run(run())
    assert started == ["motion", "person", "motion"]


def test_unsupported_by_default():
    d = Driver(1, "h", None, "", "", 0, {})

    async def run():
        for call in (d.ptz("Left"), d.goto_preset("1"), d.siren(True), d.light(True), d.recordings(None, None)):
            try:
                await call
            except NotSupported:
                continue
            raise AssertionError("should not be supported")

    asyncio.run(run())


class PresetCamera(FakeDriver):
    """Presets someone edits in the camera's own app."""
    on_camera = [{"id": "1", "name": "Driveway"}, {"id": "2", "name": "Lake"}]

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.known = list(self.on_camera)

    def presets(self):
        return self.known

    async def refresh(self):
        self.known = list(self.on_camera)


def test_presets_follow_the_camera(client, monkeypatch):
    login(client, "viewer")
    with SessionLocal() as db:
        cam = Camera(name="Deck", kind="stream", host="h", options={"main_url": "rtsp://h/main"})
        db.add(cam)
        db.commit()
        cam_id = cam.id
    driver = PresetCamera(cam_id, "h", None, "", "", 0, {})
    cams.manager.conns[cam_id] = cams.Conn(cam_id=cam_id, driver=driver, online=True)
    try:
        names = lambda: [p["name"] for c in client.get("/api/cameras").json() if c["id"] == cam_id for p in c["presets"]]
        assert names() == ["Driveway", "Lake"]
        PresetCamera.on_camera = [{"id": "2", "name": "Lake"}]   # "Driveway" deleted in the camera's app
        assert names() == ["Driveway", "Lake"]                    # within 15 s: not asked again yet
        cams.manager.conns[cam_id].refreshed = 0                  # ...time passes
        assert names() == ["Lake"]
    finally:
        cams.manager.conns.pop(cam_id, None)
        PresetCamera.on_camera = [{"id": "1", "name": "Driveway"}, {"id": "2", "name": "Lake"}]
