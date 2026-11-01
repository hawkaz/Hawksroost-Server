"""Starlink: what the dish reports, its history, and admin dish controls."""
import asyncio
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import settings_store, state
from ..db import get_db
from ..deps import admin, viewer
from ..models import StarlinkSample, User
from ..timeutil import LOCAL_TZ, iso, utcnow

router = APIRouter(tags=["starlink"])

# Dish alert flags → plain words. Unknown flags are shown with their name tidied up.
ALERTS = {
    "motors_stuck": ("Dish motors are stuck", "bad"),
    "thermal_throttle": ("Running slower because it's hot", "warn"),
    "thermal_shutdown": ("Shut down because it's too hot", "bad"),
    "mast_not_near_vertical": ("Mast isn't vertical", "warn"),
    "unexpected_location": ("Dish is somewhere unexpected", "warn"),
    "slow_ethernet_speeds": ("Ethernet cable is running slow", "warn"),
    "slow_ethernet_speeds_100": ("Ethernet link is only 100 Mbps", "warn"),
    "roaming": ("Roaming", "info"),
    "install_pending": ("Software update waiting to install", "info"),
    "is_heating": ("Heating to melt snow", "info"),
    "power_supply_thermal_throttle": ("Power supply is hot", "warn"),
    "is_power_save_idle": ("Power-save sleep", "info"),
    "moving_while_not_mobile": ("Moving on a fixed-site plan", "warn"),
    "moving_too_fast_for_policy": ("Moving too fast for the plan", "warn"),
    "dbf_telem_stale": ("Dish telemetry is stale", "info"),
    "low_motor_current": ("Low motor current", "warn"),
    "lower_signal_than_predicted": ("Signal is weaker than expected", "warn"),
    "obstruction_map_reset": ("Obstruction map was reset", "info"),
}


def _alerts(keys: list[str]) -> list[dict]:
    out = []
    for k in keys or []:
        label, level = ALERTS.get(k, (k.replace("_", " ").capitalize(), "info"))
        out.append({"key": k, "label": label, "level": level})
    return out


def _state_label(s: str | None) -> str:
    return {"CONNECTED": "Online", "SEARCHING": "Searching for satellites", "BOOTING": "Starting up",
            "STOWED": "Stowed", "SLEEPING": "Asleep (power save)", "OBSTRUCTED": "Blocked by obstructions",
            "THERMAL_SHUTDOWN": "Too hot", "NO_SATS": "No satellites", "NO_DOWNLINK": "No signal",
            "NO_PINGS": "No connection"}.get(s or "", (s or "Unknown").replace("_", " ").capitalize())


def _availability(db: Session, since: datetime) -> dict:
    out_s, secs = db.execute(select(
        func.coalesce(func.sum(StarlinkSample.outage_s), 0), func.coalesce(func.sum(StarlinkSample.seconds), 0),
    ).where(StarlinkSample.ts >= since)).one()
    return {"connected_pct": (1 - out_s / secs) * 100 if secs else None, "outage_s": out_s, "measured_s": secs}


@router.get("/api/starlink")
def starlink(db: Session = Depends(get_db), _: User = Depends(viewer)):
    cfg = settings_store.get(db, "starlink")
    row = state.get_row(db, "starlink_status")
    st = dict(row.value) if row else None
    fresh = bool(row and (utcnow() - row.updated_at).total_seconds() < 300 and not st.get("error"))
    sleep = state.get(db, "starlink_sleep")
    if sleep:
        start_local = (datetime(2000, 1, 1, tzinfo=UTC) + timedelta(minutes=sleep["start_utc_min"])).astimezone(LOCAL_TZ)
        sleep = {**sleep, "start_local": start_local.strftime("%H:%M")}
    now = utcnow()
    return {
        "enabled": cfg["enabled"],
        "reachable": fresh,
        "online": fresh and st.get("state") == "CONNECTED",
        "state_label": _state_label(st.get("state")) if fresh else ("Not reachable" if st else "No data yet"),
        "error": st.get("error") if st else None,
        "updated_at": iso(row.updated_at) if row else None,
        "status": st,
        "alerts": _alerts(st.get("alerts", [])) if st else [],
        "stats": state.get(db, "starlink_stats"),
        "sleep": sleep,
        "availability": {"day": _availability(db, now - timedelta(days=1)),
                         "week": _availability(db, now - timedelta(days=7))},
    }


@router.get("/api/starlink/live")
def live(db: Session = Depends(get_db), _: User = Depends(viewer)):
    return state.get(db, "starlink_live") or {"step_s": 5, "points": []}


@router.get("/api/starlink/map")
def obstruction_map(db: Session = Depends(get_db), _: User = Depends(viewer)):
    row = state.get_row(db, "starlink_map")
    if row is None:
        raise HTTPException(404, "No obstruction map yet.")
    return {**row.value, "updated_at": iso(row.updated_at)}


@router.get("/api/starlink/history")
def history(hours: int = 24, db: Session = Depends(get_db), _: User = Depends(viewer)):
    hours = max(1, min(hours, 24 * 31))
    bucket_s = 300 if hours <= 24 else 3600 if hours <= 24 * 8 else 6 * 3600
    since = utcnow() - timedelta(hours=hours)
    rows = db.scalars(select(StarlinkSample).where(StarlinkSample.ts >= since).order_by(StarlinkSample.ts)).all()
    buckets: dict[int, dict] = {}
    for r in rows:
        k = int(r.ts.replace(tzinfo=UTC).timestamp()) // bucket_s
        b = buckets.setdefault(k, {"lat": [], "drop": 0.0, "down": 0.0, "up": 0.0, "dpk": 0.0, "upk": 0.0,
                                   "pw": [], "out": 0, "obs": 0, "secs": 0, "n": 0})
        if r.latency_ms is not None:
            b["lat"].append(r.latency_ms)
        if r.power_w is not None:
            b["pw"].append(r.power_w)
        b["drop"] += (r.drop_rate or 0) * r.seconds
        b["down"] += (r.down_bps or 0) * r.seconds
        b["up"] += (r.up_bps or 0) * r.seconds
        b["dpk"] = max(b["dpk"], r.down_peak_bps or 0)
        b["upk"] = max(b["upk"], r.up_peak_bps or 0)
        b["out"] += r.outage_s
        b["obs"] += r.obstructed_s
        b["secs"] += r.seconds
    series = []
    for k, b in sorted(buckets.items()):
        s = b["secs"] or 1
        series.append({
            "t": datetime.fromtimestamp(k * bucket_s, UTC).isoformat().replace("+00:00", "Z"),
            "latency_ms": sorted(b["lat"])[len(b["lat"]) // 2] if b["lat"] else None,  # median
            "drop_pct": b["drop"] / s * 100,
            "down_bps": b["down"] / s, "up_bps": b["up"] / s,
            "down_peak_bps": b["dpk"], "up_peak_bps": b["upk"],
            "power_w": sum(b["pw"]) / len(b["pw"]) if b["pw"] else None,
            "outage_s": b["out"], "obstructed_s": b["obs"], "measured_s": b["secs"],
        })
    return {"bucket_s": bucket_s, "series": series}


# --- Admin: dish controls -----------------------------------------------------------------

def _ctx(db: Session):
    import starlink_grpc
    return starlink_grpc, starlink_grpc.ChannelContext(target=settings_store.get(db, "starlink")["address"])


async def _call(fn, *args, **kwargs):
    try:
        return await asyncio.wait_for(asyncio.to_thread(fn, *args, **kwargs), timeout=15)
    except Exception as e:
        raise HTTPException(502, f"The dish didn't accept that: {e}")


@router.post("/api/admin/starlink/reboot", status_code=202, dependencies=[Depends(admin)])
async def reboot(db: Session = Depends(get_db)):
    sg, ctx = _ctx(db)
    await _call(sg.reboot, context=ctx)
    return {"ok": True}


class StowIn(BaseModel):
    stow: bool


@router.post("/api/admin/starlink/stow", status_code=202, dependencies=[Depends(admin)])
async def stow(body: StowIn, db: Session = Depends(get_db)):
    sg, ctx = _ctx(db)
    await _call(sg.set_stow_state, unstow=not body.stow, context=ctx)
    return {"ok": True}


@router.post("/api/admin/starlink/reset-map", status_code=202, dependencies=[Depends(admin)])
async def reset_map(db: Session = Depends(get_db)):
    sg, ctx = _ctx(db)
    await _call(sg.reset_obstruction_map, context=ctx)
    return {"ok": True}


class SleepIn(BaseModel):
    enabled: bool
    start_local: str = Field("02:00", pattern=r"^\d{2}:\d{2}$")
    duration_min: int = Field(120, ge=15, le=24 * 60)


@router.put("/api/admin/starlink/sleep", dependencies=[Depends(admin)])
async def set_sleep(body: SleepIn, db: Session = Depends(get_db)):
    """Power-save sleep window. The dish wants minutes past midnight UTC."""
    sg, ctx = _ctx(db)
    h, m = map(int, body.start_local.split(":"))
    local = datetime.now(LOCAL_TZ).replace(hour=h, minute=m, second=0, microsecond=0)
    utc = local.astimezone(UTC)
    start = utc.hour * 60 + utc.minute
    await _call(sg.set_sleep_config, start, body.duration_min, body.enabled, context=ctx)
    state.put(db, "starlink_sleep", {"start_utc_min": start, "duration_min": body.duration_min, "enabled": body.enabled})
    return {"ok": True}
