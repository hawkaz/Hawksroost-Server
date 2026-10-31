"""Cameras: list, snapshots, PTZ, recordings, events. Admin: add/edit cameras."""
import time
from datetime import date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from reolink_aio.typings import VOD_trigger
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..db import get_db
from ..deps import admin, camera_control, optional_user, viewer
from ..models import Camera, CameraEvent, User
from ..security import can
from ..services.cameras import CameraOffline, manager, stream_names, test_connection
from ..timeutil import iso
from ..web import sign, unsign

router = APIRouter(tags=["cameras"])


def _cam_out(cam: Camera, db: Session) -> dict:
    conn = manager.conns.get(cam.id)
    last = db.scalar(select(CameraEvent).where(CameraEvent.camera_id == cam.id)
                     .order_by(CameraEvent.started_at.desc()).limit(1))
    caps = cam.capabilities or {}
    names = stream_names(cam.id)
    return {
        "id": cam.id, "name": cam.name, "model": cam.model,
        "online": bool(conn and conn.online), "last_ok_at": iso(cam.last_ok_at), "error": cam.last_error,
        "streams": {k: names[k] for k in caps.get("streams", [])},
        "ptz": bool(caps.get("ptz")), "zoom": bool(caps.get("zoom")),
        "presets": manager.presets(cam.id), "auto_track": manager.auto_track(cam.id),
        "ai_types": caps.get("ai_types", []),
        "last_event": {"type": last.type, "at": iso(last.started_at)} if last else None,
    }


@router.get("/api/cameras")
def list_cameras(db: Session = Depends(get_db), _: User = Depends(viewer)):
    cams = db.scalars(select(Camera).where(Camera.enabled).order_by(Camera.sort, Camera.id)).all()
    return [_cam_out(c, db) for c in cams]


_snap_cache: dict[int, tuple[float, bytes]] = {}


@router.get("/api/cameras/{cam_id}/snapshot")
async def snapshot(cam_id: int, _: User = Depends(viewer)):
    cached = _snap_cache.get(cam_id)
    if cached and time.monotonic() - cached[0] < 5:
        jpg = cached[1]
    else:
        try:
            jpg = await manager.snapshot(cam_id)
        except CameraOffline:
            raise HTTPException(503, "Camera is offline")
        if not jpg:
            raise HTTPException(503, "No picture from the camera")
        _snap_cache[cam_id] = (time.monotonic(), jpg)
    return Response(jpg, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=5"})


class PtzIn(BaseModel):
    command: Literal["Left", "Right", "Up", "Down", "LeftUp", "LeftDown", "RightUp", "RightDown",
                     "ZoomInc", "ZoomDec", "Stop"]
    speed: int | None = Field(None, ge=1, le=64)


@router.post("/api/cameras/{cam_id}/ptz", status_code=204)
async def ptz(cam_id: int, body: PtzIn, _: User = Depends(camera_control)):
    try:
        await manager.ptz(cam_id, body.command, body.speed)
    except CameraOffline:
        raise HTTPException(503, "Camera is offline")


class PresetIn(BaseModel):
    id: int


@router.post("/api/cameras/{cam_id}/preset", status_code=204)
async def preset(cam_id: int, body: PresetIn, _: User = Depends(camera_control)):
    try:
        await manager.goto_preset(cam_id, body.id)
    except CameraOffline:
        raise HTTPException(503, "Camera is offline")


class AutoTrackIn(BaseModel):
    enabled: bool


@router.put("/api/cameras/{cam_id}/autotrack")
async def autotrack(cam_id: int, body: AutoTrackIn, _: User = Depends(admin)):
    try:
        await manager.set_auto_track(cam_id, body.enabled)
    except CameraOffline:
        raise HTTPException(503, "Camera is offline")
    return {"auto_track": manager.auto_track(cam_id)}


# --- Recordings (from the camera's SD card) ------------------------------------------------

@router.get("/api/cameras/{cam_id}/recordings")
async def recordings(cam_id: int, day: date, _: User = Depends(viewer)):
    start = datetime(day.year, day.month, day.day)
    end = start + timedelta(days=1) - timedelta(seconds=1)
    try:
        statuses, files = await manager.recordings(cam_id, start, end, stream="sub")
    except CameraOffline:
        raise HTTPException(503, "Camera is offline")
    days = sorted({d.isoformat() for s in statuses for d in (date(s.year, s.month, x) for x in s.days)})
    out = []
    for f in files:
        out.append({
            "name": f.file_name, "start": f.start_time.isoformat(), "end": f.end_time.isoformat(),
            "start_id": f.start_time_id, "end_id": f.end_time_id,
            "duration_s": int(f.duration.total_seconds()),
            "triggers": [t.name.lower() for t in VOD_trigger if t in f.triggers and t is not VOD_trigger.TIMER],
        })
    out.sort(key=lambda x: x["start"], reverse=True)
    return {"days_with_recordings": days, "files": out}


@router.get("/api/cameras/{cam_id}/recordings/file")
async def recording_file(cam_id: int, name: str, start_id: str, end_id: str,
                         stream: Literal["main", "sub"] = "sub", download: bool = False,
                         _: User = Depends(viewer)):
    """Stream a clip from the camera's SD card through the app (the camera isn't on the internet)."""
    try:
        vod = await manager.download(cam_id, name, start_id, end_id, stream)
    except CameraOffline:
        raise HTTPException(503, "Camera is offline")

    async def body():
        try:
            async for chunk in vod.stream.iter_chunked(64 * 1024):
                yield chunk
        finally:
            vod.close()

    filename = f"camera{cam_id}-{start_id}-{stream}.mp4"
    disposition = "attachment" if download else "inline"
    headers = {"Content-Disposition": f'{disposition}; filename="{filename}"'}
    if vod.length:
        headers["Content-Length"] = str(vod.length)
    return StreamingResponse(body(), media_type="video/mp4", headers=headers)


# --- Motion events --------------------------------------------------------------------------

def signed_snapshot_url(event_id: int) -> str:
    """Notification images are fetched without the session cookie, so they carry a signature."""
    token = sign({"e": event_id, "x": int(time.time()) + 86400})
    return f"/api/cameras/events/{event_id}/snapshot?sig={token}"


@router.get("/api/cameras/{cam_id}/events")
def events(cam_id: int, limit: int = 50, db: Session = Depends(get_db), _: User = Depends(viewer)):
    rows = db.scalars(select(CameraEvent).where(CameraEvent.camera_id == cam_id)
                      .order_by(CameraEvent.started_at.desc()).limit(min(limit, 200))).all()
    return [{"id": e.id, "type": e.type, "at": iso(e.started_at),
             "snapshot": f"/api/cameras/events/{e.id}/snapshot" if e.snapshot else None} for e in rows]


@router.get("/api/cameras/events/{event_id}/snapshot")
def event_snapshot(event_id: int, sig: str | None = None, db: Session = Depends(get_db),
                   user: User | None = Depends(optional_user)):
    allowed = user is not None and can(user, "view")
    if not allowed and sig:
        data = unsign(sig)
        allowed = bool(data and data.get("e") == event_id and data.get("x", 0) > time.time())
    if not allowed:
        raise HTTPException(401)
    ev = db.get(CameraEvent, event_id)
    if ev is None or not ev.snapshot:
        raise HTTPException(404)
    path = (config.SNAPSHOT_DIR / ev.snapshot).resolve()
    if not path.is_relative_to(config.SNAPSHOT_DIR.resolve()) or not path.exists():
        raise HTTPException(404)
    return FileResponse(path, media_type="image/jpeg")


# --- Admin: manage cameras ---------------------------------------------------------------------

class CameraIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    host: str = Field(min_length=1, max_length=255)
    port: int | None = Field(None, ge=1, le=65535)
    username: str = Field(min_length=1, max_length=80)
    password: str | None = Field(None, max_length=255)  # None = keep current
    channel: int = Field(0, ge=0, le=63)
    enabled: bool = True
    sort: int = 0
    cooldown_s: int = Field(300, ge=30, le=86400)


def _admin_out(c: Camera) -> dict:
    return {"id": c.id, "name": c.name, "host": c.host, "port": c.port, "username": c.username,
            "password_set": bool(c.password), "channel": c.channel, "enabled": c.enabled,
            "sort": c.sort, "cooldown_s": c.cooldown_s, "model": c.model, "firmware": c.firmware,
            "capabilities": c.capabilities, "last_ok_at": iso(c.last_ok_at), "last_error": c.last_error}


@router.get("/api/admin/cameras", dependencies=[Depends(admin)])
def admin_cameras(db: Session = Depends(get_db)):
    return [_admin_out(c) for c in db.scalars(select(Camera).order_by(Camera.sort, Camera.id))]


@router.post("/api/admin/cameras", status_code=201, dependencies=[Depends(admin)])
def add_camera(body: CameraIn, db: Session = Depends(get_db)):
    if not body.password:
        raise HTTPException(400, "Enter the camera's password.")
    cam = Camera(**body.model_dump())
    db.add(cam)
    db.commit()
    manager.reload(cam.id)
    return _admin_out(cam)


@router.put("/api/admin/cameras/{cam_id}", dependencies=[Depends(admin)])
def edit_camera(cam_id: int, body: CameraIn, db: Session = Depends(get_db)):
    cam = db.get(Camera, cam_id)
    if cam is None:
        raise HTTPException(404)
    for k, v in body.model_dump().items():
        if k == "password" and not v:
            continue
        setattr(cam, k, v)
    db.commit()
    manager.reload(cam.id)
    return _admin_out(cam)


@router.delete("/api/admin/cameras/{cam_id}", status_code=204, dependencies=[Depends(admin)])
def delete_camera(cam_id: int, db: Session = Depends(get_db)):
    cam = db.get(Camera, cam_id)
    if cam:
        db.delete(cam)
        db.commit()
    manager.reload(cam_id)


class CameraTestIn(BaseModel):
    host: str
    port: int | None = None
    username: str
    password: str | None = None
    camera_id: int | None = None  # test with the saved password


@router.post("/api/admin/cameras/test", dependencies=[Depends(admin)])
async def test_camera(body: CameraTestIn, db: Session = Depends(get_db)):
    password = body.password
    if not password and body.camera_id:
        cam = db.get(Camera, body.camera_id)
        password = cam.password if cam else None
    if not password:
        raise HTTPException(400, "Enter the camera's password.")
    return await test_connection(body.host, body.username, password, body.port)
