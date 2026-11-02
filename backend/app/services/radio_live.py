"""Live listening: the recorder's stream from Icecast, served by the app, and a check
that it's there.

The recorder sends each dongle's sound to Icecast as mount /dev<id>: 8 kHz mono MP3 at
16 kbit/s or less, and under 4 kbit/s while nobody talks. Browsers won't start an MP3
stream until they've buffered a fair amount (Chromium about 32 KB, measured), which at
that rate took a minute or more: "Listen live never connects". So each listener first
gets PREROLL_S seconds of silence at the format's top bitrate, sent at once, then the live
stream: playback starts in about a second, PREROLL_S behind live. (Icecast's own <intro>
was tried: it sends the file slowly, so starting still took ~6 s.)

If Icecast isn't running, or the recorder can't get through to it, the Radio page says so
instead of trying, and Admin → System shows why.
"""
import logging
import subprocess
import time
from functools import cache

import httpx

from .. import config

log = logging.getLogger("hawk.radio")
PREROLL_S = 5
TRANSPORT: httpx.AsyncBaseTransport | None = None   # tests swap in a fake Icecast


@cache
def preroll() -> bytes:
    """PREROLL_S of silence in the recorder's format (8 kHz mono MP3) at 64 kbit/s, the top
    rate there, so it's the most bytes for the least delay. No ID3 tag or length header:
    a player must not think the stream is only this long."""
    try:
        return subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=8000:cl=mono",
             "-t", str(PREROLL_S), "-ac", "1", "-ar", "8000", "-c:a", "libmp3lame", "-b:a", "64k",
             "-write_xing", "0", "-id3v2_version", "0", "-f", "mp3", "pipe:1"],
            check=True, capture_output=True, timeout=30).stdout
    except Exception as e:   # no ffmpeg: the stream still plays, just slower to start
        log.warning("radio: couldn't make the live-listening lead-in (%s)", e)
        return b""


async def open_stream(mount: str) -> tuple[httpx.AsyncClient, httpx.Response] | None:
    """Connect to Icecast's mount. None if it isn't there (Icecast down, recorder not sending)."""
    client = httpx.AsyncClient(timeout=httpx.Timeout(10, read=None), transport=TRANSPORT)
    try:
        resp = await client.send(client.build_request("GET", f"{config.ICECAST_URL}/{mount}"), stream=True)
    except httpx.HTTPError:
        await client.aclose()
        return None
    if resp.status_code != 200:
        await resp.aclose()
        await client.aclose()
        return None
    return client, resp

_cache: tuple[float, set[str] | None] = (0.0, None)
CACHE_S = 5


def mounts() -> set[str] | None:
    """Mount names Icecast is serving now ({"dev1"}), or None if Icecast didn't answer."""
    global _cache
    if time.monotonic() - _cache[0] < CACHE_S:
        return _cache[1]
    found: set[str] | None
    try:
        r = httpx.get(f"{config.ICECAST_URL}/status-json.xsl", timeout=2)
        r.raise_for_status()
        sources = r.json().get("icestats", {}).get("source") or []
        if isinstance(sources, dict):   # Icecast sends one source as an object, several as a list
            sources = [sources]
        found = {s["listenurl"].rstrip("/").rsplit("/", 1)[-1] for s in sources if s.get("listenurl")}
    except (httpx.HTTPError, ValueError, KeyError, AttributeError):
        found = None
    _cache = (time.monotonic(), found)
    return found


def forget() -> None:
    global _cache
    _cache = (0.0, None)
