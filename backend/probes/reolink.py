"""Probe a camera saved in Settings → Cameras and print what it supports.

    docker compose exec api python -m probes.reolink
"""
import asyncio
import json
import sys
from datetime import datetime, timedelta

from reolink_aio.api import Host
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Camera


async def probe(cam: Camera) -> dict:
    h = Host(cam.host, cam.username, cam.password, port=cam.port, protocol="rtsp", timeout=20)
    ch = cam.channel
    out: dict = {"camera": cam.name, "host": cam.host}
    try:
        await h.get_host_data()
        await h.get_states()
        out.update(model=h.model, firmware=h.sw_version, nvr=h.is_nvr, channels=list(h.channels))
        caps = ["ptz", "pan_tilt", "zoom", "ptz_presets", "ptz_speed", "auto_track", "autotrack_stream", "ai_people"]
        out["supports"] = {c: h.supported(ch, c) for c in caps}
        out["ai_types"] = h.ai_supported_types(ch)
        out["presets"] = h.ptz_presets(ch)
        out["auto_track_enabled"] = h.auto_track_enabled(ch) if h.supported(ch, "auto_track") else None
        streams = {}
        for s in ("sub", "main", "autotrack_main", "autotrack_sub"):
            try:
                url = await h.get_rtsp_stream_source(ch, s)
                streams[s] = url.replace(cam.password, "****") if url else None
            except Exception as e:
                streams[s] = f"error: {e}"
        out["rtsp"] = streams
        end = datetime.now()
        try:
            statuses, files = await h.request_vod_files(ch, end - timedelta(hours=6), end, stream="sub")
            out["recordings_last_6h"] = len(files)
            out["recording_days"] = [str(d) for s in statuses for d in s][:40]
            if files:
                f = files[0]
                out["sample_recording"] = {"name": f.file_name, "start": str(f.start_time), "duration_s": f.duration.total_seconds()}
        except Exception as e:
            out["recordings_error"] = str(e)
        try:
            await h.baichuan.subscribe_events()
            out["push_events"] = "ok"
            await h.baichuan.unsubscribe_events()
        except Exception as e:
            out["push_events"] = f"failed: {e}"
    except Exception as e:
        out["error"] = str(e)
    finally:
        try:
            await h.logout()
        except Exception:
            pass
    return out


async def main() -> None:
    with SessionLocal() as db:
        cams = db.scalars(select(Camera).order_by(Camera.id)).all()
    if not cams:
        print("No cameras saved yet. Add one in the app: Settings → Cameras.")
        sys.exit(1)
    for cam in cams:
        print(json.dumps(await probe(cam), indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
