"""Register camera streams with go2rtc through its API.

Camera addresses and passwords live in the app's database, so go2rtc's own
config file stays generic; the app pushes stream sources at runtime.
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
