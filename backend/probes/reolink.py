"""Probe the Reolink cameras saved in Admin → Cameras and print what they support.

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
        caps = ["ptz", "pan_tilt", "zoom", "zoom_basic", "ptz_presets", "ptz_preset_basic", "ptz_speed", "auto_track",
                "autotrack_stream", "ai_people", "siren", "siren_play", "floodLight", "replay"]
        out["supports"] = {c: h.supported(ch, c) for c in caps}
        # What the camera says about zooming (decides whether the app can offer camera-side zoom).
        out["zoom_api"] = {k: h.api_version(k, ch) for k in ("ptzType", "supportDigitalZoom", "supportPtz3DLocation")}
        try:
            out["zoom_api"]["range"] = h.zoom_range(ch)
        except Exception as e:
            out["zoom_api"]["range"] = f"none ({type(e).__name__})"
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
        cams = db.scalars(select(Camera).where(Camera.kind == "reolink").order_by(Camera.id)).all()
    if not cams:
        print("No Reolink cameras saved yet. Add one in the app: Admin → Cameras.")
        sys.exit(1)
    for cam in cams:
        print(json.dumps(await probe(cam), indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
