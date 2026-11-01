"""Camera drivers. Each kind of camera says what it can do (capabilities) and
does it; the manager and the UI only use what a camera reports.

- reolink: Reolink cameras, NVRs and Home Hubs via reolink_aio — streams, PTZ,
  presets, auto-tracking, AI detections, SD-card recordings, siren, spotlight.
- onvif:   most other IP cameras via the ONVIF standard (onvif-zeep-async) —
  streams, snapshot, PTZ, presets, motion/person events.
- stream:  anything with a video URL (RTSP/HTTP) — view only.
"""
import asyncio
import datetime as dt
import logging
from collections.abc import Callable
from urllib.parse import quote, urlsplit, urlunsplit

import httpx

from ... import config

log = logging.getLogger("hawk.cameras")

PTZ_COMMANDS = ("Left", "Right", "Up", "Down", "LeftUp", "LeftDown", "RightUp", "RightDown", "ZoomInc", "ZoomDec", "Stop")
OnChange = Callable[[set[str]], None]


class NotSupported(Exception):
    pass


def with_credentials(url: str, user: str, password: str) -> str:
    """Put a username/password into a stream URL that came back without them."""
    if not url or not user:
        return url
    parts = urlsplit(url)
    if parts.username:
        return url
    netloc = f"{quote(user, safe='')}:{quote(password or '', safe='')}@{parts.hostname}"
    if parts.port:
        netloc += f":{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


async def go2rtc_frame(stream: str) -> bytes | None:
    """A JPEG of any stream, made by go2rtc (works for cameras without a snapshot URL)."""
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{config.GO2RTC_URL}/api/frame.jpeg", params={"src": stream})
            return r.content if r.status_code == 200 and r.content else None
    except httpx.HTTPError:
        return None


class Driver:
    """Base: everything is unsupported unless a driver overrides it."""
    kind = "base"

    def __init__(self, cam_id: int, host: str, port: int | None, username: str, password: str,
                 channel: int, options: dict):
        self.cam_id, self.host, self.port = cam_id, host, port
        self.username, self.password, self.channel = username, password, channel
        self.options = options or {}

    async def connect(self) -> dict:
        """Returns {"model", "firmware", "caps": {...}, "streams": {"main"|"sub"|"tele": url}}."""
        raise NotImplementedError

    async def watch(self, on_change: OnChange) -> None:
        """Run until the connection breaks, reporting the set of active detections."""
        while True:
            await asyncio.sleep(120)
            await self.keepalive()

    async def keepalive(self) -> None:
        pass

    async def snapshot(self, full: bool = False) -> bytes | None:
        return await go2rtc_frame(f"cam{self.cam_id}_{'main' if full else 'sub'}")

    def presets(self) -> list[dict]:
        return []

    async def refresh(self) -> None:
        """Re-read things people change in the camera's own app (e.g. presets)."""

    def auto_track(self) -> bool | None:
        return None

    def light_on(self) -> bool | None:
        """Whether the camera's light is on now; None when it has no light."""
        return None

    async def ptz(self, command: str, speed: int | None = None) -> None:
        raise NotSupported()

    async def goto_preset(self, preset_id: str) -> None:
        raise NotSupported()

    async def set_auto_track(self, enable: bool) -> None:
        raise NotSupported()

    async def recordings(self, start, end) -> dict:
        """{"days_with_recordings": [iso dates], "files": [{name, start, end, start_id, end_id, duration_s, triggers}]}"""
        raise NotSupported()

    async def download(self, name: str, start_id: str, end_id: str, stream: str):
        raise NotSupported()

    vod_kind = "Playback"

    async def vod_url(self, name: str, stream: str, start_id: str, end_id: str) -> str:
        """URL on the camera that plays a recording in a browser (supports byte ranges)."""
        raise NotSupported()

    async def renew_session(self) -> None:
        """Log in again (an expired login makes the camera answer with an error page)."""

    async def siren(self, on: bool) -> None:
        raise NotSupported()

    async def light(self, on: bool) -> None:
        raise NotSupported()

    async def close(self) -> None:
        pass


# --- Reolink ------------------------------------------------------------------------------

class ReolinkDriver(Driver):
    kind = "reolink"
    AI = {"person": "people", "vehicle": "vehicle", "animal": "dog_cat"}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        from reolink_aio.api import Host
        self.h = Host(self.host, self.username, self.password, port=self.port, protocol="rtsp", stream="sub", timeout=20)
        self.push_ok = False
        self.lock = asyncio.Lock()
        self._main_names: dict[str, str] = {}

    async def connect(self) -> dict:
        h, ch = self.h, self.channel
        await h.get_host_data()
        await h.get_states()
        caps = {
            "ptz": h.supported(ch, "pan_tilt") or h.supported(ch, "ptz"),
            "zoom": h.supported(ch, "zoom"),
            # Can have presets (even if none are saved yet); the list itself is re-read by refresh().
            "presets": h.supported(ch, "ptz_preset_basic") or h.supported(ch, "ptz_presets"),
            "auto_track": h.supported(ch, "auto_track"),
            "recordings": True,   # reads the camera's SD card (or the NVR's disk)
            "events": True,
            "ai_types": [k for k, v in self.AI.items() if v in (h.ai_supported_types(ch) or [])],
            "siren": h.supported(ch, "siren_play"),
            "light": h.supported(ch, "floodLight"),
        }
        streams = {"sub": await h.get_rtsp_stream_source(ch, "sub"),
                   "main": await h.get_rtsp_stream_source(ch, "main")}
        if caps["auto_track"]:
            # Dual-lens tracking cameras expose the zoom lens as an extra stream. [VERIFY with the probe]
            streams["tele"] = await h.get_rtsp_stream_source(ch, "autotrack_main", check=True)
        model = h.camera_model(ch) if h.is_nvr else h.model
        extra = {"name": h.camera_name(ch), "channels": list(h.channels), "nvr": h.is_nvr}
        return {"model": model, "firmware": h.sw_version, "caps": caps, "streams": streams, "extra": extra}

    def _active(self) -> set[str]:
        h, ch = self.h, self.channel
        on = set()
        for ours, theirs in self.AI.items():
            try:
                if h.ai_detected(ch, theirs):
                    on.add(ours)
            except Exception:
                pass
        if h.motion_detected(ch):
            on.add("motion")
        return on

    async def watch(self, on_change: OnChange) -> None:
        h = self.h
        try:
            await h.baichuan.subscribe_events()
            h.baichuan.register_callback(f"hawk-{self.cam_id}", lambda: on_change(self._active()))
            self.push_ok = True
        except Exception as e:
            log.info("camera %s: push events unavailable (%s); polling instead", self.cam_id, e)
        while True:
            if self.push_ok:
                await asyncio.sleep(120)
                await h.baichuan.check_subscribe_events()
                await h.get_states()
                await self.refresh()
            else:
                await asyncio.sleep(3)
                await h.get_ai_state_all_ch()
                await h.get_motion_state_all_ch()
                on_change(self._active())

    async def snapshot(self, full: bool = False) -> bytes | None:
        return await self.h.get_snapshot(self.channel, "main" if full else "sub")

    def presets(self) -> list[dict]:
        return [{"id": str(i), "name": n} for n, i in self.h.ptz_presets(self.channel).items()]

    async def refresh(self) -> None:
        if self.h.supported(self.channel, "ptz_preset_basic") or self.h.supported(self.channel, "ptz_presets"):
            await self.h.get_state(cmd="GetPtzPreset")
        if self.h.supported(self.channel, "floodLight"):
            await self.h.get_state(cmd="GetWhiteLed")

    def light_on(self) -> bool | None:
        return self.h.whiteled_state(self.channel) if self.h.supported(self.channel, "floodLight") else None

    def auto_track(self) -> bool | None:
        return self.h.auto_track_enabled(self.channel) if self.h.supported(self.channel, "auto_track") else None

    async def ptz(self, command: str, speed: int | None = None) -> None:
        if not self.h.supported(self.channel, "ptz_speed"):
            speed = None
        await self.h.set_ptz_command(self.channel, command=command, speed=speed)

    async def goto_preset(self, preset_id: str) -> None:
        await self.h.set_ptz_command(self.channel, preset=int(preset_id))

    async def set_auto_track(self, enable: bool) -> None:
        await self.h.set_auto_tracking(self.channel, enable)

    async def recordings(self, start, end) -> dict:
        from reolink_aio.typings import VOD_trigger
        async with self.lock:
            statuses, files = await self.h.request_vod_files(self.channel, start, end, stream="sub")
        days = sorted({dt.date(s.year, s.month, d).isoformat() for s in statuses for d in s.days})
        out = [{
            "name": f.file_name, "start": f.start_time.isoformat(), "end": f.end_time.isoformat(),
            "start_id": f.start_time_id, "end_id": f.end_time_id,
            "duration_s": int(f.duration.total_seconds()),
            "triggers": [t.name.lower() for t in VOD_trigger if t in f.triggers and t is not VOD_trigger.TIMER],
        } for f in files]
        out.sort(key=lambda x: x["start"], reverse=True)
        return {"days_with_recordings": days, "files": out}

    async def _file_for(self, name: str, stream: str, start_id: str, end_id: str) -> str:
        """Recording lists come from the small (sub) stream. For full quality, find the
        main-stream file of the same recording (RecS… vs RecM… names). [VERIFY on the camera]"""
        if stream != "main" or "RecS" not in name:
            return name
        if name in self._main_names:
            return self._main_names[name]
        try:
            start = dt.datetime.strptime(start_id, "%Y%m%d%H%M%S")
            end = dt.datetime.strptime(end_id, "%Y%m%d%H%M%S")
            async with self.lock:
                _, files = await self.h.request_vod_files(self.channel, start - dt.timedelta(minutes=1),
                                                          end + dt.timedelta(minutes=1), stream="main")
        except Exception as e:
            log.info("camera %s: no full-quality match for %s (%s)", self.cam_id, name, e)
            return name
        for f in files:
            if f.start_time_id == start_id:
                self._main_names[name] = f.file_name
                return f.file_name
        return name

    async def download(self, name: str, start_id: str, end_id: str, stream: str):
        name = await self._file_for(name, stream, start_id, end_id)
        return await self.h.download_vod(name, start_time=start_id, end_time=end_id, channel=self.channel, stream=stream)

    async def vod_url(self, name: str, stream: str, start_id: str, end_id: str) -> str:
        from reolink_aio.enums import VodRequestType
        name = await self._file_for(name, stream, start_id, end_id)
        _mime, url = await self.h.get_vod_source(self.channel, name, stream, VodRequestType(self.vod_kind))
        return url

    async def renew_session(self) -> None:
        await self.h.expire_session(unsubscribe=False)

    async def siren(self, on: bool) -> None:
        await self.h.set_siren(self.channel, on)   # on: sounds twice, then stops by itself

    async def light(self, on: bool) -> None:
        await self.h.set_whiteled(self.channel, state=on)

    async def close(self) -> None:
        try:
            if self.push_ok:
                self.push_ok = False
                await self.h.baichuan.unsubscribe_events()
            await self.h.logout()
        except Exception:
            pass


# --- ONVIF --------------------------------------------------------------------------------

def onvif_detection(topic: str) -> str | None:
    """Map an ONVIF event topic to our detection names. Brands name these differently."""
    t = topic.lower()
    if any(k in t for k in ("people", "human", "person", "face")):
        return "person"
    if any(k in t for k in ("vehicle", "car")):
        return "vehicle"
    if any(k in t for k in ("dogcat", "animal", "pet")):
        return "animal"
    if "motion" in t:
        return "motion"
    return None


class OnvifDriver(Driver):
    kind = "onvif"
    # Pan/tilt/zoom direction → velocity (x = pan, y = tilt).
    VECTORS = {"Left": (-1, 0), "Right": (1, 0), "Up": (0, 1), "Down": (0, -1), "LeftUp": (-1, 1),
               "LeftDown": (-1, -1), "RightUp": (1, 1), "RightDown": (1, -1)}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.cam = None
        self.ptz_svc = None
        self.main_token = self.sub_token = None
        self._presets: list[dict] = []
        self.active: dict[str, bool] = {}

    async def connect(self) -> dict:
        from onvif import ONVIFCamera
        self.cam = ONVIFCamera(self.host, self.port or 80, self.username, self.password, adjust_time=True)
        await self.cam.update_xaddrs()
        dev = await self.cam.create_devicemgmt_service()
        info = await dev.GetDeviceInformation()
        media = await self.cam.create_media_service()
        profiles = await media.GetProfiles()
        h264 = [p for p in profiles if getattr(getattr(p, "VideoEncoderConfiguration", None), "Encoding", None) == "H264"]
        usable = h264 or list(profiles)
        if not usable:
            raise RuntimeError("The camera reported no video profiles.")

        def pixels(p):
            res = getattr(getattr(p, "VideoEncoderConfiguration", None), "Resolution", None)
            return (res.Width * res.Height) if res else 0
        usable.sort(key=pixels, reverse=True)
        main, sub = usable[0], usable[-1]
        self.main_token, self.sub_token = main.token, sub.token

        async def uri(token):
            r = await media.GetStreamUri({"ProfileToken": token,
                                          "StreamSetup": {"Stream": "RTP-Unicast", "Transport": {"Protocol": "RTSP"}}})
            return with_credentials(r.Uri, self.username, self.password)
        streams = {"main": await uri(main.token)}
        if sub.token != main.token:
            streams["sub"] = await uri(sub.token)
        else:
            streams["sub"] = streams["main"]

        caps = {"ptz": False, "zoom": False, "presets": False, "auto_track": False, "recordings": False,
                "events": False, "ai_types": [], "siren": False, "light": False}
        if getattr(main, "PTZConfiguration", None) is not None:
            try:
                self.ptz_svc = await self.cam.create_ptz_service()
                caps["ptz"] = True
                try:
                    nodes = await self.ptz_svc.GetNodes()
                    caps["zoom"] = any(getattr(n.SupportedPTZSpaces, "ContinuousZoomVelocitySpace", None) for n in nodes)
                except Exception:
                    pass
                await self._load_presets()
                caps["presets"] = True
            except Exception as e:
                log.info("camera %s: no PTZ (%s)", self.cam_id, e)
                self.ptz_svc = None
        try:
            device_caps = await self.cam.get_capabilities() or {}
            caps["events"] = bool((device_caps.get("Events") or {}).get("WSPullPointSupport", True))
        except Exception:
            caps["events"] = True  # many cameras under-report; we try anyway
        model = " ".join(x for x in (getattr(info, "Manufacturer", None), getattr(info, "Model", None)) if x)
        return {"model": model or None, "firmware": getattr(info, "FirmwareVersion", None), "caps": caps,
                "streams": streams}

    async def _load_presets(self) -> None:
        presets = await self.ptz_svc.GetPresets({"ProfileToken": self.main_token}) or []
        self._presets = [{"id": str(p.token), "name": getattr(p, "Name", None) or f"Preset {p.token}"} for p in presets]

    async def watch(self, on_change: OnChange) -> None:
        lost = asyncio.Event()
        try:
            mgr = await self.cam.create_pullpoint_manager(dt.timedelta(minutes=10), lost.set)
            await mgr.set_synchronization_point()
            svc = mgr.get_service()
        except Exception as e:
            log.info("camera %s: no ONVIF events (%s); live view and controls still work", self.cam_id, e)
            return await super().watch(on_change)
        try:
            while not lost.is_set():
                r = await svc.PullMessages({"MessageLimit": 100, "Timeout": dt.timedelta(seconds=60)})
                changed = False
                for m in getattr(r, "NotificationMessage", None) or []:
                    topic = str(getattr(getattr(m, "Topic", None), "_value_1", "") or "")
                    kind = onvif_detection(topic)
                    if not kind:
                        continue
                    items = getattr(getattr(getattr(m.Message, "_value_1", None), "Data", None), "SimpleItem", None) or []
                    on = any(str(getattr(i, "Value", "")).lower() in ("true", "1") for i in items)
                    if self.active.get(kind) != on:
                        self.active[kind] = on
                        changed = True
                if changed:
                    on_change({k for k, v in self.active.items() if v})
            raise RuntimeError("Event subscription ended; reconnecting")
        finally:
            try:
                await mgr.stop()
            except Exception:
                pass

    async def snapshot(self, full: bool = False) -> bytes | None:
        token = self.main_token if full else self.sub_token
        try:
            jpg = await self.cam.get_snapshot(token)
            if jpg:
                return jpg
        except Exception:
            pass
        return await super().snapshot(full)

    def presets(self) -> list[dict]:
        return self._presets

    async def refresh(self) -> None:
        if self.ptz_svc:
            await self._load_presets()

    async def ptz(self, command: str, speed: int | None = None) -> None:
        if not self.ptz_svc:
            raise NotSupported()
        if command == "Stop":
            await self.ptz_svc.Stop({"ProfileToken": self.main_token, "PanTilt": True, "Zoom": True})
            return
        v = (speed or 32) / 64
        if command in ("ZoomInc", "ZoomDec"):
            vel = {"PanTilt": {"x": 0.0, "y": 0.0}, "Zoom": {"x": v if command == "ZoomInc" else -v}}
        else:
            px, py = self.VECTORS[command]
            vel = {"PanTilt": {"x": px * v, "y": py * v}, "Zoom": {"x": 0.0}}
        await self.ptz_svc.ContinuousMove({"ProfileToken": self.main_token, "Velocity": vel,
                                           "Timeout": dt.timedelta(seconds=10)})

    async def goto_preset(self, preset_id: str) -> None:
        if not self.ptz_svc:
            raise NotSupported()
        await self.ptz_svc.GotoPreset({"ProfileToken": self.main_token, "PresetToken": preset_id})

    async def close(self) -> None:
        if self.cam:
            try:
                await self.cam.close()
            except Exception:
                pass
            self.cam, self.ptz_svc = None, None


# --- Plain stream URL ---------------------------------------------------------------------

class StreamDriver(Driver):
    kind = "stream"

    async def connect(self) -> dict:
        main = with_credentials(self.options.get("main_url", ""), self.username, self.password)
        if not main:
            raise RuntimeError("Enter the camera's video address.")
        sub = with_credentials(self.options.get("sub_url", ""), self.username, self.password) or main
        caps = {"ptz": False, "zoom": False, "presets": False, "auto_track": False, "recordings": False,
                "events": False, "ai_types": [], "siren": False, "light": False}
        return {"model": None, "firmware": None, "caps": caps, "streams": {"main": main, "sub": sub}}

    async def snapshot(self, full: bool = False) -> bytes | None:
        url = self.options.get("snapshot_url")
        if url:
            auth = httpx.DigestAuth(self.username, self.password) if self.username else None
            try:
                async with httpx.AsyncClient(timeout=10, auth=auth) as c:
                    r = await c.get(url)
                    if r.status_code == 401 and self.username:
                        r = await c.get(url, auth=(self.username, self.password))
                    if r.status_code == 200 and r.content:
                        return r.content
            except httpx.HTTPError:
                pass
        return await super().snapshot(full)


DRIVERS: dict[str, type[Driver]] = {"reolink": ReolinkDriver, "onvif": OnvifDriver, "stream": StreamDriver}


def make_driver(cam) -> Driver:
    cls = DRIVERS.get(cam.kind or "reolink", ReolinkDriver)
    return cls(cam.id, cam.host, cam.port, cam.username or "", cam.password or "", cam.channel or 0, cam.options or {})
