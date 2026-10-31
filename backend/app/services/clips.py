"""Short clips cut from the camera's long SD-card recordings.

The camera records 24/7 into long files. Downloading a whole one over
Starlink is slow, so the laptop fetches the file from the camera over the
LAN, cuts out just the part asked for with ffmpeg (no re-encoding), and
serves that. Jobs run in the background so a slow fetch never ties up a
request (or trips a phone's network timeout).
"""
import asyncio
import logging
import secrets
import shutil
import time
from dataclasses import dataclass, field

from .. import config
from .cameras import manager

log = logging.getLogger("hawk.clips")
KEEP_S = 2 * 3600          # clips and cached source files live this long
MAX_JOBS = 3


@dataclass
class Job:
    id: str
    cam_id: int
    status: str = "fetching"      # fetching | cutting | ready | failed
    error: str | None = None
    progress: float = 0.0          # bytes fetched / total, while fetching
    size: int = 0
    created: float = field(default_factory=time.time)
    filename: str = "clip.mp4"


jobs: dict[str, Job] = {}


def _source_path(cam_id: int, name: str, stream: str):
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)[-120:]
    return config.CLIPS_DIR / f"src-cam{cam_id}-{stream}-{safe}.mp4"


async def _fetch(job: Job, name: str, start_id: str, end_id: str, stream: str):
    path = _source_path(job.cam_id, name, stream)
    if path.exists() and path.stat().st_size > 0:
        path.touch()
        return path
    vod = await manager.download(job.cam_id, name, start_id, end_id, stream)
    tmp = path.with_suffix(".part")
    got = 0
    try:
        with tmp.open("wb") as f:
            async for chunk in vod.stream.iter_chunked(256 * 1024):
                f.write(chunk)
                got += len(chunk)
                if vod.length:
                    job.progress = got / vod.length
    finally:
        vod.close()
    tmp.replace(path)
    return path


async def _run(job: Job, name: str, start_id: str, end_id: str, stream: str, offset_s: float, length_s: float):
    try:
        src = await _fetch(job, name, start_id, end_id, stream)
        job.status = "cutting"
        out = config.CLIPS_DIR / f"clip-{job.id}.mp4"
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{max(0.0, offset_s):.2f}", "-i", str(src), "-t", f"{length_s:.2f}",
            "-c", "copy", "-movflags", "+faststart", str(out),
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
        _, err = await proc.communicate()
        if proc.returncode != 0 or not out.exists():
            raise RuntimeError(err.decode(errors="replace")[-300:] or "ffmpeg failed")
        job.size = out.stat().st_size
        job.status = "ready"
    except Exception as e:  # camera offline, bad file, ffmpeg error
        log.warning("clip %s failed: %s", job.id, e)
        job.status, job.error = "failed", "Couldn't make that clip. The camera may be busy or offline; try again."


def start(cam_id: int, cam_name: str, name: str, start_id: str, end_id: str, stream: str,
          offset_s: float, length_s: float, label: str) -> Job:
    cleanup()
    busy = [j for j in jobs.values() if j.status in ("fetching", "cutting")]
    if len(busy) >= MAX_JOBS:
        raise RuntimeError("A few clips are already being made. Try again in a minute.")
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("Clips need ffmpeg, which isn't installed on the server.")
    config.CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    job = Job(id=secrets.token_urlsafe(9), cam_id=cam_id,
              filename=f"{cam_name}-{label}.mp4".replace(" ", "_").replace("/", "-"))
    jobs[job.id] = job
    asyncio.get_running_loop().create_task(_run(job, name, start_id, end_id, stream, offset_s, length_s))
    return job


def clip_path(job: Job):
    return config.CLIPS_DIR / f"clip-{job.id}.mp4"


def cleanup() -> None:
    """Drop clips and cached camera files older than KEEP_S."""
    now = time.time()
    for jid, job in list(jobs.items()):
        if now - job.created > KEEP_S:
            clip_path(job).unlink(missing_ok=True)
            jobs.pop(jid, None)
    if config.CLIPS_DIR.exists():
        for f in config.CLIPS_DIR.iterdir():
            if now - f.stat().st_mtime > KEEP_S:
                f.unlink(missing_ok=True)
