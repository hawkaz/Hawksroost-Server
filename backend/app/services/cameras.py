"""Reolink cameras via reolink_aio: connection, streams, PTZ, recordings, motion events.

Cameras are added in Settings → Cameras. On connect we read the camera's
capabilities, hand its RTSP sources to go2rtc, and subscribe to its TCP push
events (no webhook or inbound port needed). If push events fail we poll.
"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, timedelta
from pathlib import Path

from reolink_aio.api import Host
from sqlalchemy import select

from .. import config, push, settings_store
from ..db import SessionLocal
from ..models import AlertPref, Camera, CameraEvent, User
from ..timeutil import LOCAL_TZ, utcnow
from . import go2rtc

log = logging.getLogger("hawk.cameras")

# Our detection names → reolink_aio AI type names.
AI_TYPES = {"person": "people", "vehicle": "vehicle", "animal": "dog_cat"}
REFRESH_S = 120
POLL_S = 3


def stream_names(cam_id: int) -> dict[str, str]:
    return {"sub": f"cam{cam_id}_sub", "main": f"cam{cam_id}_main", "tele": f"cam{cam_id}_tele"}


@dataclass
class Conn:
    cam_id: int
    host: Host
    channel: int
    online: bool = False
    push_ok: bool = False
    active: set[str] = field(default_factory=set)       # detection types currently on
    last_event: dict[str, float] = field(default_factory=dict)
    task: asyncio.Task | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class CameraManager:
    def __init__(self) -> None:
        self.conns: dict[int, Conn] = {}
        self.last_push: dict[tuple[int, int], float] = {}   # (user, camera) → monotonic time
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
        """(Re)connect a camera after it's added or edited. Safe to call any time."""
        asyncio.get_running_loop().create_task(self._reload(cam_id))

    async def _reload(self, cam_id: int) -> None:
        await self._disconnect(cam_id)
        with SessionLocal() as db:
            cam = db.get(Camera, cam_id)
            if cam is None or not cam.enabled:
                for name in stream_names(cam_id).values():
                    await go2rtc.remove_stream(name)
                return
            host = Host(cam.host, cam.username, cam.password, port=cam.port, protocol="rtsp", stream="sub", timeout=20)
            conn = Conn(cam_id=cam.id, host=host, channel=cam.channel)
        self.conns[cam_id] = conn
        conn.task = asyncio.get_running_loop().create_task(self._run(conn))

    async def _disconnect(self, cam_id: int) -> None:
        conn = self.conns.pop(cam_id, None)
        if conn is None:
            return
        if conn.task:
            conn.task.cancel()
        try:
            if conn.push_ok:
                await conn.host.baichuan.unsubscribe_events()
            await conn.host.logout()
        except Exception:
            pass

    # --- connection loop -------------------------------------------------------------

    async def _run(self, conn: Conn) -> None:
        backoff = 10
        while True:
            try:
                await self._connect(conn)
                backoff = 10
                while True:
                    await asyncio.sleep(POLL_S if not conn.push_ok else REFRESH_S)
                    if conn.push_ok:
                        await conn.host.baichuan.check_subscribe_events()
                        await conn.host.get_states()
                    else:
                        await conn.host.get_ai_state_all_ch()
                        await conn.host.get_motion_state_all_ch()
                        self._evaluate(conn)
                    self._mark(conn.cam_id, ok=True)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                conn.online = False
                log.warning("camera %s: %s", conn.cam_id, e)
                self._mark(conn.cam_id, ok=False, error=_friendly(e))
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 300)

    async def _connect(self, conn: Conn) -> None:
        h, ch = conn.host, conn.channel
        await h.get_host_data()
        await h.get_states()
        caps = {
            "model": h.camera_model(ch) if h.is_nvr else h.model,
            "ptz": h.supported(ch, "pan_tilt") or h.supported(ch, "ptz"),
            "zoom": h.supported(ch, "zoom"),
            "presets": h.supported(ch, "ptz_presets"),
            "auto_track": h.supported(ch, "auto_track"),
            "ai_types": [k for k, v in AI_TYPES.items() if v in (h.ai_supported_types(ch) or [])],
            "streams": [],
        }
        names = stream_names(conn.cam_id)
        sources = {
            "sub": await h.get_rtsp_stream_source(ch, "sub"),
            "main": await h.get_rtsp_stream_source(ch, "main"),
        }
        if caps["auto_track"]:
            # TrackMix telephoto lens. [VERIFY] with backend/probes/reolink_probe.py
            sources["tele"] = await h.get_rtsp_stream_source(ch, "autotrack_main", check=True)
        for key, src in sources.items():
            if src and await go2rtc.set_stream(names[key], src):
                caps["streams"].append(key)
        try:
            await h.baichuan.subscribe_events()
            h.baichuan.register_callback(f"hawk-{conn.cam_id}", lambda: self._on_push(conn))
            conn.push_ok = True
        except Exception as e:
            log.info("camera %s: push events unavailable (%s); polling instead", conn.cam_id, e)
            conn.push_ok = False
        conn.online = True
        with SessionLocal() as db:
            cam = db.get(Camera, conn.cam_id)
            if cam:
                cam.model, cam.firmware, cam.capabilities = caps["model"], h.sw_version, caps
                cam.last_ok_at, cam.last_error = utcnow(), None
                db.commit()
        log.info("camera %s connected: %s", conn.cam_id, caps)

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

    def _on_push(self, conn: Conn) -> None:
        # Called synchronously by reolink_aio from its socket reader.
        self._evaluate(conn)

    def _evaluate(self, conn: Conn) -> None:
        h, ch = conn.host, conn.channel
        now_on = set()
        for ours, theirs in AI_TYPES.items():
            try:
                if h.ai_detected(ch, theirs):
                    now_on.add(ours)
            except Exception:
                pass
        if h.motion_detected(ch):
            now_on.add("motion")
        started = now_on - conn.active
        conn.active = now_on
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
            jpg = await conn.host.get_snapshot(conn.channel, "sub")
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
        from ..routers.cameras import signed_snapshot_url  # avoid import cycle
        image = signed_snapshot_url(ev.id) if ev.snapshot else None
        local = now.replace(tzinfo=UTC).astimezone(LOCAL_TZ)
        ev.notified = await push.send_to_users(db, targets, title, f"{local:%-I:%M %p} · tap to look",
                                               url=f"/cameras/{cam.id}", tag=f"cam-{cam.id}", image=image)
        db.commit()

    # --- actions used by the API -------------------------------------------------------

    def get(self, cam_id: int) -> Conn:
        conn = self.conns.get(cam_id)
        if conn is None or not conn.online:
            raise CameraOffline()
        return conn

    async def snapshot(self, cam_id: int, stream: str = "sub") -> bytes | None:
        conn = self.get(cam_id)
        return await conn.host.get_snapshot(conn.channel, stream)

    async def ptz(self, cam_id: int, command: str, speed: int | None = None) -> None:
        conn = self.get(cam_id)
        if not conn.host.supported(conn.channel, "ptz_speed"):
            speed = None
        await conn.host.set_ptz_command(conn.channel, command=command, speed=speed)

    async def goto_preset(self, cam_id: int, preset_id: int) -> None:
        conn = self.get(cam_id)
        await conn.host.set_ptz_command(conn.channel, preset=preset_id)

    def presets(self, cam_id: int) -> list[dict]:
        conn = self.conns.get(cam_id)
        if conn is None or not conn.online:
            return []
        return [{"id": i, "name": n} for n, i in conn.host.ptz_presets(conn.channel).items()]

    def auto_track(self, cam_id: int) -> bool | None:
        conn = self.conns.get(cam_id)
        if conn is None or not conn.online or not conn.host.supported(conn.channel, "auto_track"):
            return None
        return conn.host.auto_track_enabled(conn.channel)

    async def set_auto_track(self, cam_id: int, enable: bool) -> None:
        conn = self.get(cam_id)
        await conn.host.set_auto_tracking(conn.channel, enable)

    async def recordings(self, cam_id: int, start, end, stream: str = "sub"):
        conn = self.get(cam_id)
        async with conn.lock:
            return await conn.host.request_vod_files(conn.channel, start, end, stream=stream)

    async def download(self, cam_id: int, file_name: str, start_id: str, end_id: str, stream: str):
        conn = self.get(cam_id)
        return await conn.host.download_vod(
            file_name, start_time=start_id, end_time=end_id, channel=conn.channel, stream=stream)


class CameraOffline(Exception):
    pass


async def test_connection(host: str, username: str, password: str, port: int | None) -> dict:
    """Used by Settings → Cameras → Test before saving."""
    h = Host(host, username, password, port=port, timeout=15)
    try:
        await h.get_host_data()
        return {"ok": True, "model": h.model, "firmware": h.sw_version, "name": h.camera_name(0),
                "channels": list(h.channels), "nvr": h.is_nvr}
    except Exception as e:
        return {"ok": False, "error": _friendly(e)}
    finally:
        try:
            await h.logout()
        except Exception:
            pass


def _friendly(e: Exception) -> str:
    text = str(e) or type(e).__name__
    low = text.lower()
    if "login" in low or "credential" in low or "password" in low:
        return "Wrong username or password."
    if "timeout" in low or "timed out" in low:
        return "No answer from the camera. Check the address and that it's powered."
    if "connect" in low or "unreachable" in low or "refused" in low:
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
