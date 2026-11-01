"""Cameras: list, snapshots, controls, recordings, events. Admin: add/edit cameras.

What a camera offers (pan/tilt, presets, recordings, siren, ...) comes from its
driver's capabilities, so the UI never assumes a brand. CameraOffline (503) and
NotSupported (400) are turned into responses in main.py.
"""
import time
from datetime import date, datetime, timedelta
from typing import Literal

from urllib.parse import unquote, urlsplit, urlunsplit

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..db import get_db
from ..deps import admin, camera_control, optional_user, viewer
from ..models import Camera, CameraEvent, User
from ..security import can
from ..services import clips
from ..services.cameras import KINDS, PTZ_COMMANDS, manager, stream_names, test_connection
from ..timeutil import LOCAL_TZ, iso
from ..web import sign, unsign

router = APIRouter(tags=["cameras"])


def _cam_out(cam: Camera, db: Session) -> dict:
    last = db.scalar(select(CameraEvent).where(CameraEvent.camera_id == cam.id)
                     .order_by(CameraEvent.started_at.desc()).limit(1))
    caps = cam.capabilities or {}
    names = stream_names(cam.id)
    return {
        "id": cam.id, "name": cam.name, "model": cam.model,
        "online": manager.online(cam.id), "last_ok_at": iso(cam.last_ok_at), "error": cam.last_error,
        "streams": {k: names[k] for k in caps.get("streams", [])},
        "ptz": bool(caps.get("ptz")), "zoom": bool(caps.get("zoom")),
        "presets": manager.presets(cam.id), "auto_track": manager.auto_track(cam.id),
        "recordings": bool(caps.get("recordings")), "events": bool(caps.get("events")),
        "siren": bool(caps.get("siren")), "light": bool(caps.get("light")),
        "ai_types": caps.get("ai_types", []),
        "last_event": {"type": last.type, "at": iso(last.started_at)} if last else None,
    }


@router.get("/api/cameras")
def list_cameras(db: Session = Depends(get_db), _: User = Depends(viewer)):
    cams = db.scalars(select(Camera).where(Camera.enabled).order_by(Camera.sort, Camera.id)).all()
    return [_cam_out(c, db) for c in cams]


_snap_cache: dict[int, tuple[float, bytes]] = {}


@router.get("/api/cameras/{cam_id}/snapshot")
async def snapshot(cam_id: int, full: bool = False, download: bool = False,
                   db: Session = Depends(get_db), _: User = Depends(viewer)):
    """Small still for tiles (cached 5 s), or a full-quality picture to save."""
    cached = _snap_cache.get(cam_id)
    if not full and cached and time.monotonic() - cached[0] < 5:
        jpg = cached[1]
    else:
        jpg = await manager.snapshot(cam_id, full)
        if not jpg:
            raise HTTPException(503, "No picture from the camera")
        if not full:
            _snap_cache[cam_id] = (time.monotonic(), jpg)
    headers = {"Cache-Control": "private, max-age=5"}
    if download:
        cam = db.get(Camera, cam_id)
        stamp = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d-%H%M%S")
        headers["Content-Disposition"] = f'attachment; filename="{(cam.name if cam else "camera").replace(" ", "_")}-{stamp}.jpg"'
    return Response(jpg, media_type="image/jpeg", headers=headers)


class PtzIn(BaseModel):
    command: str = Field(pattern="^(" + "|".join(PTZ_COMMANDS) + ")$")
    speed: int | None = Field(None, ge=1, le=64)


@router.post("/api/cameras/{cam_id}/ptz", status_code=204)
async def ptz(cam_id: int, body: PtzIn, _: User = Depends(camera_control)):
    await manager.ptz(cam_id, body.command, body.speed)


class PresetIn(BaseModel):
    id: str = Field(min_length=1, max_length=64)


@router.post("/api/cameras/{cam_id}/preset", status_code=204)
async def preset(cam_id: int, body: PresetIn, _: User = Depends(camera_control)):
    await manager.goto_preset(cam_id, body.id)


class OnOffIn(BaseModel):
    on: bool


@router.post("/api/cameras/{cam_id}/siren", status_code=204)
async def siren(cam_id: int, body: OnOffIn, _: User = Depends(camera_control)):
    await manager.siren(cam_id, body.on)


@router.post("/api/cameras/{cam_id}/light", status_code=204)
async def light(cam_id: int, body: OnOffIn, _: User = Depends(camera_control)):
    await manager.light(cam_id, body.on)


class AutoTrackIn(BaseModel):
    enabled: bool


@router.put("/api/cameras/{cam_id}/autotrack")
async def autotrack(cam_id: int, body: AutoTrackIn, _: User = Depends(admin)):
    await manager.set_auto_track(cam_id, body.enabled)
    return {"auto_track": manager.auto_track(cam_id)}


# --- Recordings (from the camera's SD card) ------------------------------------------------

@router.get("/api/cameras/{cam_id}/recordings")
async def recordings(cam_id: int, day: date, _: User = Depends(viewer)):
    start = datetime(day.year, day.month, day.day)
    end = start + timedelta(days=1) - timedelta(seconds=1)
    return await manager.recordings(cam_id, start, end)


@router.get("/api/cameras/{cam_id}/recordings/file")
async def recording_file(cam_id: int, name: str, start_id: str, end_id: str,
                         stream: Literal["main", "sub"] = "sub", download: bool = False,
                         _: User = Depends(viewer)):
    """Stream a recording from the camera through the app (the camera isn't on the internet)."""
    vod = await manager.download(cam_id, name, start_id, end_id, stream)

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


# --- Clips: a short piece of a long recording ------------------------------------------------

class ClipIn(BaseModel):
    name: str
    start_id: str
    end_id: str
    stream: Literal["main", "sub"] = "sub"
    offset_s: float = Field(0, ge=0, le=24 * 3600)
    length_s: float = Field(60, ge=5, le=30 * 60)
    label: str = Field("clip", max_length=40)


def _job_out(job: clips.Job) -> dict:
    out = {"id": job.id, "status": job.status, "error": job.error, "progress": round(job.progress, 3), "size": job.size}
    if job.status == "ready":
        out["url"] = f"/api/cameras/clips/{job.id}"
    return out


@router.post("/api/cameras/{cam_id}/clips", status_code=202)
def make_clip(cam_id: int, body: ClipIn, db: Session = Depends(get_db), _: User = Depends(viewer)):
    cam = db.get(Camera, cam_id)
    if cam is None:
        raise HTTPException(404)
    try:
        job = clips.start(cam_id, cam.name, body.name, body.start_id, body.end_id, body.stream,
                          body.offset_s, body.length_s, body.label)
    except RuntimeError as e:
        raise HTTPException(429, str(e))
    return _job_out(job)


@router.get("/api/cameras/clips/{job_id}/status")
def clip_status(job_id: str, _: User = Depends(viewer)):
    job = clips.jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "That clip has expired. Make it again.")
    return _job_out(job)


@router.get("/api/cameras/clips/{job_id}")
def clip_file(job_id: str, download: bool = False, _: User = Depends(viewer)):
    job = clips.jobs.get(job_id)
    if job is None or job.status != "ready" or not clips.clip_path(job).exists():
        raise HTTPException(404, "That clip has expired. Make it again.")
    return FileResponse(clips.clip_path(job), media_type="video/mp4",
                        filename=job.filename if download else None,
                        content_disposition_type="attachment" if download else "inline")


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
def event_snapshot(event_id: int, sig: str | None = None, download: bool = False, db: Session = Depends(get_db),
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
    name = f"motion-{ev.type}-{ev.started_at:%Y%m%d-%H%M%S}.jpg" if download else None
    return FileResponse(path, media_type="image/jpeg", filename=name,
                        content_disposition_type="attachment" if download else "inline")


# --- Admin: manage cameras ---------------------------------------------------------------------

def split_credentials(url: str) -> tuple[str, str, str]:
    """rtsp://user:pass@host/x → (rtsp://host/x, user, pass). The login is kept in its own fields."""
    parts = urlsplit(url.strip())
    if not parts.username:
        return url.strip(), "", ""
    netloc = parts.hostname or ""
    if parts.port:
        netloc += f":{parts.port}"
    clean = urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    return clean, unquote(parts.username), unquote(parts.password or "")


class CameraOptions(BaseModel):
    main_url: str = Field("", max_length=500)
    sub_url: str = Field("", max_length=500)
    snapshot_url: str = Field("", max_length=500)


class CameraIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: Literal["reolink", "onvif", "stream"] = "reolink"
    host: str = Field("", max_length=255)
    port: int | None = Field(None, ge=1, le=65535)
    username: str = Field("", max_length=80)
    password: str | None = Field(None, max_length=255)  # None/empty = keep current
    channel: int = Field(0, ge=0, le=63)
    options: CameraOptions = CameraOptions()
    enabled: bool = True
    sort: int = 0
    cooldown_s: int = Field(300, ge=30, le=86400)

    @model_validator(mode="after")
    def check(self):
        self.host = self.host.strip()
        if self.kind == "stream":
            o = self.options
            for key in ("main_url", "sub_url", "snapshot_url"):
                url, user, pw = split_credentials(getattr(o, key))
                setattr(o, key, url)
                if user and not self.username:
                    self.username, self.password = user, pw
            if not o.main_url:
                raise ValueError("Enter the camera's video address.")
            if urlsplit(o.main_url).scheme not in ("rtsp", "rtsps", "http", "https", "rtmp"):
                raise ValueError("The video address should start with rtsp:// or http://")
            self.host = urlsplit(o.main_url).hostname or ""
        else:
            if not self.host:
                raise ValueError("Enter the camera's address.")
            if not self.username:
                raise ValueError("Enter the camera's username.")
            self.options = CameraOptions()
        return self


def _admin_out(c: Camera) -> dict:
    return {"id": c.id, "name": c.name, "kind": c.kind, "host": c.host, "port": c.port, "username": c.username,
            "password_set": bool(c.password), "channel": c.channel, "options": c.options or {},
            "enabled": c.enabled, "sort": c.sort, "cooldown_s": c.cooldown_s, "model": c.model,
            "firmware": c.firmware, "capabilities": c.capabilities, "last_ok_at": iso(c.last_ok_at),
            "last_error": c.last_error}


@router.get("/api/admin/cameras/kinds", dependencies=[Depends(admin)])
def camera_kinds():
    return [{"id": k, "label": v} for k, v in KINDS.items()]


@router.get("/api/admin/cameras", dependencies=[Depends(admin)])
def admin_cameras(db: Session = Depends(get_db)):
    return [_admin_out(c) for c in db.scalars(select(Camera).order_by(Camera.sort, Camera.id))]


@router.post("/api/admin/cameras", status_code=201, dependencies=[Depends(admin)])
def add_camera(body: CameraIn, db: Session = Depends(get_db)):
    if body.kind != "stream" and not body.password:
        raise HTTPException(400, "Enter the camera's password.")
    data = body.model_dump()
    data["password"] = data["password"] or ""
    cam = Camera(**data)
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
    if body.kind == "stream" and not body.username:
        cam.password = ""   # no login, so don't keep an old password around
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


class CameraTestIn(CameraIn):
    name: str = "test"
    camera_id: int | None = None  # test with the saved password


@router.post("/api/admin/cameras/test", dependencies=[Depends(admin)])
async def test_camera(body: CameraTestIn, db: Session = Depends(get_db)):
    password = body.password
    if not password and body.camera_id:
        cam = db.get(Camera, body.camera_id)
        password = cam.password if cam else None
    if not password and body.kind != "stream":
        raise HTTPException(400, "Enter the camera's password.")
    return await test_connection(body.kind, body.host, body.port, body.username, password or "",
                                 body.channel, body.options.model_dump())
