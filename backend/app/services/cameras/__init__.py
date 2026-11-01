"""Cameras: keeps each enabled camera connected through its driver.

Cameras are added in Admin → Cameras. On connect the driver reports what the
camera can do and its video sources; the sources go to go2rtc, the
capabilities are saved on the camera row (the UI only shows what a camera can
do), and the driver then watches for detections. Started detections become
events with a snapshot and, for people who asked, a notification.
"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, timedelta
from pathlib import Path

import httpx
from sqlalchemy import select

from ... import config, push, settings_store
from ...db import SessionLocal
from ...models import AlertPref, Camera, CameraEvent, User
from ...timeutil import LOCAL_TZ, utcnow
from .. import go2rtc
from .drivers import KINDS, PTZ_COMMANDS, Driver, NotSupported, go2rtc_frame, make_driver

__all__ = ["KINDS", "PTZ_COMMANDS", "CameraOffline", "NotSupported", "RecordingUnavailable", "cleanup_old_events",
           "manager", "stream_names", "test_connection"]

log = logging.getLogger("hawk.cameras")
HEARTBEAT_S = 120


def stream_names(cam_id: int) -> dict[str, str]:
    return {"sub": f"cam{cam_id}_sub", "main": f"cam{cam_id}_main", "tele": f"cam{cam_id}_tele"}


class CameraOffline(Exception):
    pass


class RecordingUnavailable(Exception):
    pass


VOD_TRANSPORT: httpx.AsyncBaseTransport | None = None   # tests swap in a fake camera
# Reolink sends video/mp4, or octet-stream (sometimes spelled "apolication").
VIDEO_TYPES = {"video/mp4", "application/octet-stream", "apolication/octet-stream"}


@dataclass
class Conn:
    cam_id: int
    driver: Driver
    online: bool = False
    active: set[str] = field(default_factory=set)        # detections currently on
    last_event: dict[str, float] = field(default_factory=dict)
    task: asyncio.Task | None = None
    refreshed: float = 0.0                               # loop time of the last refresh()


class CameraManager:
    def __init__(self) -> None:
        self.conns: dict[int, Conn] = {}
        self.last_push: dict[tuple[int, int], float] = {}   # (user, camera) → loop time
        self._loop: asyncio.AbstractEventLoop | None = None

    # --- lifecycle ---------------------------------------------------------------

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        with SessionLocal() as db:
            ids = [c.id for c in db.scalars(select(Camera).where(Camera.enabled))]
        for cam_id in ids:
            self.reload(cam_id)

    async def stop(self) -> None:
        for cam_id in list(self.conns):
            await self._disconnect(cam_id)

    def reload(self, cam_id: int) -> None:
        """(Re)connect a camera after it's added, edited or removed. Safe to call any time,
        including from plain (threaded) route handlers."""
        coro = self._reload(cam_id)
        try:
            asyncio.get_running_loop().create_task(coro)
        except RuntimeError:  # not on the event loop thread
            if self._loop is None:
                coro.close()
                return
            asyncio.run_coroutine_threadsafe(coro, self._loop)

    async def _reload(self, cam_id: int) -> None:
        await self._disconnect(cam_id)
        with SessionLocal() as db:
            cam = db.get(Camera, cam_id)
            if cam is None or not cam.enabled:
                await go2rtc.preload(stream_names(cam_id)["sub"], on=False)
                for name in stream_names(cam_id).values():
                    await go2rtc.remove_stream(name)
                return
            conn = Conn(cam_id=cam.id, driver=make_driver(cam))
        self.conns[cam_id] = conn
        conn.task = asyncio.get_running_loop().create_task(self._run(conn))

    async def _disconnect(self, cam_id: int) -> None:
        conn = self.conns.pop(cam_id, None)
        if conn is None:
            return
        if conn.task:
            conn.task.cancel()
        await conn.driver.close()

    # --- connection loop -------------------------------------------------------------

    async def _run(self, conn: Conn) -> None:
        backoff = 10
        while True:
            try:
                await self._connect(conn)
                backoff = 10
                watcher = asyncio.get_running_loop().create_task(
                    conn.driver.watch(lambda active: self._on_change(conn, active)))
                try:
                    while not watcher.done():
                        self._mark(conn.cam_id, ok=True)
                        await asyncio.wait({watcher}, timeout=HEARTBEAT_S)
                    watcher.result()   # re-raises whatever ended it
                    raise RuntimeError("Lost the connection")
                finally:
                    watcher.cancel()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                conn.online = False
                log.warning("camera %s: %s", conn.cam_id, e)
                self._mark(conn.cam_id, ok=False, error=_friendly(e))
                await conn.driver.close()
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 300)

    async def _connect(self, conn: Conn) -> None:
        info = await conn.driver.connect()
        names = stream_names(conn.cam_id)
        registered = []
        for key, name in names.items():
            src = info["streams"].get(key)
            if src and await go2rtc.set_stream(name, src):
                registered.append(key)
            elif not src:
                await go2rtc.remove_stream(name)
        if "sub" in registered:
            # Live view opens on the small stream; keeping it connected inside the cabin
            # network means the picture starts at the camera's next keyframe.
            await go2rtc.preload(names["sub"])
        caps = {**info["caps"], "streams": registered}
        conn.online = True
        with SessionLocal() as db:
            cam = db.get(Camera, conn.cam_id)
            if cam:
                cam.model, cam.firmware, cam.capabilities = info.get("model"), info.get("firmware"), caps
                cam.last_ok_at, cam.last_error = utcnow(), None
                db.commit()
        log.info("camera %s connected (%s): %s", conn.cam_id, conn.driver.kind, caps)

    def _mark(self, cam_id: int, ok: bool, error: str | None = None) -> None:
        with SessionLocal() as db:
            cam = db.get(Camera, cam_id)
            if cam:
                if ok:
                    cam.last_ok_at, cam.last_error = utcnow(), None
                else:
                    cam.last_error = error
                db.commit()

    # --- events ----------------------------------------------------------------------

    def _on_change(self, conn: Conn, active: set[str]) -> None:
        """Drivers call this (sometimes from a socket callback) with what's detected right now."""
        started = active - conn.active
        conn.active = set(active)
        for kind in started:
            assert self._loop is not None
            self._loop.create_task(self._event(conn, kind))

    async def _event(self, conn: Conn, kind: str) -> None:
        loop_now = asyncio.get_running_loop().time()
        with SessionLocal() as db:
            cam = db.get(Camera, conn.cam_id)
            if cam is None:
                return
            cooldown = cam.cooldown_s or settings_store.get(db, "alerts")["default_cooldown_s"]
            if loop_now - conn.last_event.get(kind, -1e9) < cooldown:
                return
            conn.last_event[kind] = loop_now
            snap_rel = await self._save_snapshot(conn, kind)
            ev = CameraEvent(camera_id=cam.id, type=kind, snapshot=snap_rel)
            db.add(ev)
            db.commit()
            await self._notify(db, cam, ev, loop_now, cooldown)

    async def _save_snapshot(self, conn: Conn, kind: str) -> str | None:
        try:
            jpg = await conn.driver.snapshot()
        except Exception:
            return None
        if not jpg:
            return None
        rel = Path(f"cam{conn.cam_id}") / f"{utcnow():%Y%m%d-%H%M%S}-{kind}.jpg"
        path = config.SNAPSHOT_DIR / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(jpg)
        return str(rel)

    async def _notify(self, db, cam: Camera, ev: CameraEvent, loop_now: float, cooldown: int) -> None:
        now = utcnow()
        prefs = db.scalars(select(AlertPref).where(AlertPref.camera_id == cam.id, AlertPref.enabled)).all()
        targets = []
        for p in prefs:
            user = db.get(User, p.user_id)
            if not user or not user.active or push.is_muted(user, now):
                continue
            if p.mute_until and p.mute_until > now:
                continue
            if ev.type not in (p.types or []):
                continue
            if loop_now - self.last_push.get((user.id, cam.id), -1e9) < cooldown:
                continue
            self.last_push[(user.id, cam.id)] = loop_now
            targets.append(user.id)
        if not targets:
            return
        words = {"person": "Someone", "vehicle": "A vehicle", "animal": "An animal", "motion": "Motion"}
        title = f"{words.get(ev.type, 'Motion')} at the {cam.name} camera"
        from ...routers.cameras import signed_snapshot_url  # avoid import cycle
        image = signed_snapshot_url(ev.id) if ev.snapshot else None
        local = now.replace(tzinfo=UTC).astimezone(LOCAL_TZ)
        ev.notified = await push.send_to_users(db, targets, title, f"{local:%-I:%M %p} · tap to look",
                                               url=f"/cameras/{cam.id}", tag=f"cam-{cam.id}", image=image)
        db.commit()

    # --- actions used by the API -------------------------------------------------------
    # Each raises CameraOffline when the camera isn't connected and NotSupported
    # when this kind of camera can't do it.

    async def refresh(self, cam_id: int, max_age_s: float = 15) -> None:
        """Re-read what people change in the camera's own app (presets), at most every max_age_s.
        Never raises: a slow or failing camera just keeps what it had."""
        conn = self.conns.get(cam_id)
        if conn is None or not conn.online:
            return
        now = asyncio.get_running_loop().time()
        if now - conn.refreshed < max_age_s:
            return
        conn.refreshed = now
        try:
            await asyncio.wait_for(conn.driver.refresh(), timeout=5)
        except Exception as e:
            log.info("camera %s: refresh failed (%s)", cam_id, e)

    def online(self, cam_id: int) -> bool:
        conn = self.conns.get(cam_id)
        return bool(conn and conn.online)

    def _driver(self, cam_id: int) -> Driver:
        conn = self.conns.get(cam_id)
        if conn is None or not conn.online:
            raise CameraOffline()
        return conn.driver

    async def snapshot(self, cam_id: int, full: bool = False) -> bytes | None:
        conn = self.conns.get(cam_id)
        if conn is None:
            raise CameraOffline()
        if not conn.online:
            # go2rtc may still reach the stream even when the control connection is down.
            return await go2rtc_frame(stream_names(cam_id)["main" if full else "sub"])
        return await conn.driver.snapshot(full)

    async def ptz(self, cam_id: int, command: str, speed: int | None = None) -> None:
        await self._driver(cam_id).ptz(command, speed)

    async def goto_preset(self, cam_id: int, preset_id: str) -> None:
        await self._driver(cam_id).goto_preset(preset_id)

    def presets(self, cam_id: int) -> list[dict]:
        return self.conns[cam_id].driver.presets() if self.online(cam_id) else []

    def light_on(self, cam_id: int) -> bool | None:
        return self.conns[cam_id].driver.light_on() if self.online(cam_id) else None

    def auto_track(self, cam_id: int) -> bool | None:
        return self.conns[cam_id].driver.auto_track() if self.online(cam_id) else None

    async def set_auto_track(self, cam_id: int, enable: bool) -> None:
        await self._driver(cam_id).set_auto_track(enable)

    async def recordings(self, cam_id: int, start, end) -> dict:
        return await self._driver(cam_id).recordings(start, end)

    async def download(self, cam_id: int, file_name: str, start_id: str, end_id: str, stream: str):
        return await self._driver(cam_id).download(file_name, start_id, end_id, stream)

    async def open_recording(self, cam_id: int, name: str, stream: str, start_id: str, end_id: str,
                             headers: dict[str, str]) -> tuple[httpx.AsyncClient, httpx.Response]:
        """Open a recording on the camera for playing, passing the browser's Range header
        through so playback starts at once and seeking works. The caller closes both."""
        driver = self._driver(cam_id)
        client = httpx.AsyncClient(verify=False, timeout=httpx.Timeout(20, read=60), transport=VOD_TRANSPORT)
        try:
            for _ in range(3):
                url = await driver.vod_url(name, stream, start_id, end_id)
                resp = await client.send(client.build_request("GET", url, headers=headers), stream=True)
                ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                if ctype == "video/x-flv" and driver.vod_kind == "Playback":
                    await resp.aclose()
                    driver.vod_kind = "Download"   # this camera's Playback sends FLV; browsers need MP4
                    continue
                if resp.status_code in (200, 206) and ctype in VIDEO_TYPES:
                    return client, resp
                log.info("camera %s: recording answer %s %s; logging in again", cam_id, resp.status_code, ctype)
                await resp.aclose()
                await driver.renew_session()
            raise RecordingUnavailable()
        except BaseException:
            await client.aclose()
            raise

    async def siren(self, cam_id: int, on: bool) -> None:
        await self._driver(cam_id).siren(on)

    async def light(self, cam_id: int, on: bool) -> None:
        await self._driver(cam_id).light(on)


async def test_connection(kind: str, host: str, port: int | None, username: str, password: str,
                          channel: int, options: dict) -> dict:
    """Used by Admin → Cameras → Test before saving. Connects, reports, disconnects."""
    probe = Camera(id=0, kind=kind, host=host, port=port, username=username, password=password,
                   channel=channel, options=options)
    driver = make_driver(probe)
    try:
        info = await asyncio.wait_for(driver.connect(), timeout=30)
        if kind == "stream":
            # Nothing to log in to, so prove the video address works by grabbing a frame.
            name = "hawk_test"
            if not await go2rtc.set_stream(name, info["streams"]["main"]):
                return {"ok": False, "error": "The video service isn't running."}
            try:
                if not await go2rtc_frame(name):
                    return {"ok": False, "error": "No picture from that address. Check it and the login."}
            finally:
                await go2rtc.remove_stream(name)
        return {"ok": True, "model": info.get("model"), "firmware": info.get("firmware"),
                "caps": info["caps"], "streams": sorted(k for k, v in info["streams"].items() if v),
                **info.get("extra", {})}
    except Exception as e:
        return {"ok": False, "error": _friendly(e)}
    finally:
        await driver.close()


def _friendly(e: Exception) -> str:
    text = str(e) or type(e).__name__
    low = text.lower()
    if "login" in low or "credential" in low or "password" in low or "not authorized" in low or "401" in low:
        return "Wrong username or password."
    if "timeout" in low or "timed out" in low or isinstance(e, TimeoutError):
        return "No answer from the camera. Check the address and that it's powered."
    if "connect" in low or "unreachable" in low or "refused" in low or "name or service" in low:
        return "Can't reach the camera at that address."
    return text[:200]


def cleanup_old_events(days: int = 30) -> int:
    cutoff = utcnow() - timedelta(days=days)
    with SessionLocal() as db:
        old = db.scalars(select(CameraEvent).where(CameraEvent.started_at < cutoff)).all()
        for ev in old:
            if ev.snapshot:
                (config.SNAPSHOT_DIR / ev.snapshot).unlink(missing_ok=True)
            db.delete(ev)
        db.commit()
        return len(old)


manager = CameraManager()
