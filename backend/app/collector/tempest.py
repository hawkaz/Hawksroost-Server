"""Tempest hub UDP listener (port 50222).

Message formats follow https://apidocs.tempestwx.com/reference/tempest-udp-broadcast
"""
import asyncio
import json
import logging
from datetime import UTC, datetime

from .. import settings_store, state
from ..db import SessionLocal
from ..models import WeatherEvent, WeatherObs

log = logging.getLogger("hawk.tempest")
PORT = 50222

# obs_st array positions
OBS_FIELDS = [
    "ts", "wind_lull", "wind_avg", "wind_gust", "wind_dir", None, "pressure_mb", "temp_c",
    "humidity", "illuminance", "uv", "solar", "rain_mm", "precip_type", "strike_avg_km",
    "strike_count", "battery", None,
]


def _ts(epoch: float) -> datetime:
    return datetime.fromtimestamp(epoch, UTC).replace(tzinfo=None)


def parse_obs(values: list) -> dict:
    out = {}
    for i, name in enumerate(OBS_FIELDS):
        if name and i < len(values):
            out[name] = values[i]
    out["ts"] = _ts(out["ts"])
    return out


def handle(msg: dict) -> None:
    kind = msg.get("type")
    with SessionLocal() as db:
        cfg = settings_store.get(db, "tempest")
        if not cfg["enabled"]:
            return
        serial = msg.get("serial_number")
        if cfg["serial"] and serial and serial != cfg["serial"] and kind != "hub_status":
            return
        seen = state.get(db, "tempest_devices") or {}
        if serial and serial not in seen:
            seen[serial] = kind
            state.put(db, "tempest_devices", seen)

        if kind == "obs_st":
            for values in msg.get("obs", []):
                obs = parse_obs(values)
                db.add(WeatherObs(serial=serial, **obs))
                live = {k: v for k, v in obs.items() if k != "ts"}
                live["ts"] = obs["ts"].isoformat() + "Z"
                state.put(db, "tempest_obs", live, commit=False)
            db.commit()
        elif kind == "rapid_wind":
            t, speed, direction = msg["ob"]
            state.put(db, "tempest_wind", {"ts": _ts(t).isoformat() + "Z", "speed": speed, "dir": direction})
        elif kind == "evt_strike":
            t, distance, energy = msg["evt"]
            db.add(WeatherEvent(ts=_ts(t), kind="strike", distance_km=distance, energy=energy))
            db.commit()
        elif kind == "evt_precip":
            db.add(WeatherEvent(ts=_ts(msg["evt"][0]), kind="rain_start"))
            db.commit()
        elif kind in ("hub_status", "device_status"):
            state.put(db, f"tempest_{kind}", {k: v for k, v in msg.items() if k != "type"})


class _Protocol(asyncio.DatagramProtocol):
    def datagram_received(self, data, addr):
        try:
            handle(json.loads(data))
        except Exception:
            log.exception("bad Tempest packet from %s", addr)


async def run() -> None:
    loop = asyncio.get_running_loop()
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind(("0.0.0.0", PORT))
    await loop.create_datagram_endpoint(_Protocol, sock=sock)
    log.info("Listening for Tempest on UDP %s", PORT)
    await asyncio.Event().wait()
