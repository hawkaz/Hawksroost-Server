"""Register camera streams with go2rtc through its API.

Cameras are set up in the app (Admin → Cameras), which pushes each stream to
go2rtc at runtime. Note: go2rtc saves streams added this way into its own
config file (data/go2rtc/go2rtc.yaml), stream logins included. That file lives
in the gitignored data folder on the laptop and is never served.
"""
import logging

import httpx

from .. import config

log = logging.getLogger("hawk.go2rtc")


async def set_stream(name: str, src: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.put(f"{config.GO2RTC_URL}/api/streams", params={"name": name, "src": src})
            if r.status_code >= 400:
                # Older builds want PATCH to replace an existing stream.
                r = await c.patch(f"{config.GO2RTC_URL}/api/streams", params={"name": name, "src": src})
            return r.status_code < 400
    except httpx.HTTPError as e:
        log.warning("go2rtc not reachable: %s", e)
        return False


async def preload(name: str, on: bool = True) -> bool:
    """Keep (or stop keeping) a stream connected to its camera even with nobody watching,
    so opening the camera doesn't wait for the camera to start a stream. Traffic stays on
    the cabin network. go2rtc 1.9.11+; it only works while the camera answers."""
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await (c.put if on else c.delete)(f"{config.GO2RTC_URL}/api/preload", params={"src": name})
            return r.status_code < 400
    except httpx.HTTPError as e:
        log.info("go2rtc preload %s: %s", name, e)
        return False


async def remove_stream(name: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            await c.delete(f"{config.GO2RTC_URL}/api/streams", params={"src": name})
    except httpx.HTTPError:
        pass


async def list_streams() -> dict:
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{config.GO2RTC_URL}/api/streams")
            return r.json() if r.status_code == 200 else {}
    except (httpx.HTTPError, ValueError):
        return {}
