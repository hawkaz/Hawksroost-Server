"""Tempest weather and Starlink status. Values are metric; the browser converts for display."""
import logging
import time
from datetime import UTC, datetime, timedelta

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import settings_store, state
from ..db import get_db
from ..deps import viewer
from ..models import StarlinkSample, WeatherEvent, WeatherObs
from ..timeutil import LOCAL_TZ, iso, utcnow

log = logging.getLogger("hawk.weather")
router = APIRouter(tags=["weather"], dependencies=[Depends(viewer)])

FORECAST_URL = "https://swd.weatherflow.com/swd/rest/better_forecast"
_forecast_cache: dict = {"at": 0.0, "key": None, "data": None}


def _local_midnight_utc(days_ago: int = 0) -> datetime:
    d = datetime.now(LOCAL_TZ).date() - timedelta(days=days_ago)
    return datetime(d.year, d.month, d.day, tzinfo=LOCAL_TZ).astimezone(UTC).replace(tzinfo=None)


async def _forecast(cfg: dict) -> dict | None:
    """Tempest's forecast API, if a token and station are configured. Cached 30 min."""
    if not (cfg["api_token"] and cfg["station_id"]):
        return None
    key = (cfg["api_token"], cfg["station_id"])
    if _forecast_cache["key"] == key and time.monotonic() - _forecast_cache["at"] < 1800:
        return _forecast_cache["data"]
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(FORECAST_URL, params={
                "station_id": cfg["station_id"], "token": cfg["api_token"],
                "units_temp": "c", "units_wind": "mps", "units_pressure": "mb", "units_precip": "mm",
                "units_distance": "km"})
            r.raise_for_status()
            raw = r.json()
        days = [{
            "date": datetime.fromtimestamp(d["day_start_local"], LOCAL_TZ).date().isoformat(),
            "conditions": d.get("conditions"), "icon": d.get("icon"),
            "high_c": d.get("air_temp_high"), "low_c": d.get("air_temp_low"),
            "precip_pct": d.get("precip_probability"),
        } for d in raw.get("forecast", {}).get("daily", [])[:7]]
        data = {"days": days, "conditions": raw.get("current_conditions", {}).get("conditions")}
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as e:
        log.warning("Tempest forecast failed: %s", e)
        data = None
    _forecast_cache.update(at=time.monotonic(), key=key, data=data)
    return data


@router.get("/api/weather")
async def weather_now(db: Session = Depends(get_db)):
    cfg = settings_store.get(db, "tempest")
    obs = state.get_row(db, "tempest_obs")
    wind = state.get(db, "tempest_wind")
    rain_today = db.scalar(select(func.sum(WeatherObs.rain_mm)).where(WeatherObs.ts >= _local_midnight_utc())) or 0
    since = utcnow() - timedelta(hours=3)
    strikes = db.execute(select(func.count(), func.min(WeatherEvent.distance_km), func.max(WeatherEvent.ts))
                         .where(WeatherEvent.kind == "strike", WeatherEvent.ts >= since)).one()
    return {
        "enabled": cfg["enabled"],
        "units": settings_store.get(db, "general")["units"],
        "now": obs.value if obs else None,
        "updated_at": iso(obs.updated_at) if obs else None,
        "wind": wind,
        "rain_today_mm": rain_today,
        "lightning": {"count_3h": strikes[0], "nearest_km": strikes[1], "last": iso(strikes[2])},
        "forecast": await _forecast(cfg),
    }


@router.get("/api/weather/history")
def weather_history(hours: int = 24, db: Session = Depends(get_db)):
    hours = max(1, min(hours, 24 * 31))
    bucket_min = 10 if hours <= 48 else 60 if hours <= 24 * 8 else 180
    since = utcnow() - timedelta(hours=hours)
    rows = db.scalars(select(WeatherObs).where(WeatherObs.ts >= since).order_by(WeatherObs.ts)).all()
    buckets: dict[int, dict] = {}
    for r in rows:
        k = int(r.ts.replace(tzinfo=UTC).timestamp()) // (bucket_min * 60)
        b = buckets.setdefault(k, {"n": 0, "temp": 0.0, "hum": 0.0, "press": 0.0, "wind": 0.0, "gust": 0.0, "rain": 0.0})
        b["n"] += 1
        b["temp"] += r.temp_c or 0
        b["hum"] += r.humidity or 0
        b["press"] += r.pressure_mb or 0
        b["wind"] += r.wind_avg or 0
        b["gust"] = max(b["gust"], r.wind_gust or 0)
        b["rain"] += r.rain_mm or 0
    series = [{
        "t": datetime.fromtimestamp(k * bucket_min * 60, UTC).isoformat().replace("+00:00", "Z"),
        "temp_c": b["temp"] / b["n"], "humidity": b["hum"] / b["n"], "pressure_mb": b["press"] / b["n"],
        "wind_avg": b["wind"] / b["n"], "wind_gust": b["gust"], "rain_mm": b["rain"],
    } for k, b in sorted(buckets.items())]

    daily_rain = []
    for days_ago in range(6, -1, -1):
        start, end = _local_midnight_utc(days_ago), _local_midnight_utc(days_ago - 1)
        total = db.scalar(select(func.sum(WeatherObs.rain_mm)).where(WeatherObs.ts >= start, WeatherObs.ts < end))
        daily_rain.append({"date": (datetime.now(LOCAL_TZ).date() - timedelta(days=days_ago)).isoformat(),
                           "rain_mm": total or 0})
    strikes = db.scalars(select(WeatherEvent).where(WeatherEvent.kind == "strike", WeatherEvent.ts >= since)
                         .order_by(WeatherEvent.ts.desc()).limit(200)).all()
    return {"bucket_min": bucket_min, "series": series, "daily_rain": daily_rain,
            "strikes": [{"t": iso(s.ts), "distance_km": s.distance_km} for s in strikes]}


def _cycle_start(billing_day: int) -> datetime:
    today = datetime.now(LOCAL_TZ).date()
    day = max(1, min(int(billing_day or 1), 28))
    start = today.replace(day=day)
    if start > today:
        prev_month = (today.replace(day=1) - timedelta(days=1))
        start = prev_month.replace(day=day)
    return datetime(start.year, start.month, start.day, tzinfo=LOCAL_TZ).astimezone(UTC).replace(tzinfo=None)


@router.get("/api/starlink")
def starlink(db: Session = Depends(get_db)):
    cfg = settings_store.get(db, "starlink")
    status = state.get_row(db, "starlink_status")

    def usage(since: datetime) -> dict:
        down, up, secs = db.execute(select(
            func.coalesce(func.sum(StarlinkSample.down_bytes), 0),
            func.coalesce(func.sum(StarlinkSample.up_bytes), 0),
            func.coalesce(func.sum(StarlinkSample.seconds), 0),
        ).where(StarlinkSample.ts >= since)).one()
        return {"down_bytes": down, "up_bytes": up, "covered_s": secs}

    since = utcnow() - timedelta(hours=24)
    rows = db.scalars(select(StarlinkSample).where(StarlinkSample.ts >= since).order_by(StarlinkSample.ts)).all()
    series, bucket = [], None
    for r in rows:  # 15-minute buckets
        key = r.ts.replace(minute=r.ts.minute - r.ts.minute % 15)
        if bucket is None or bucket["key"] != key:
            bucket = {"key": key, "lat": [], "down": 0.0, "up": 0.0, "secs": 0}
            series.append(bucket)
        if r.latency_ms is not None:
            bucket["lat"].append(r.latency_ms)
        bucket["down"] += r.down_bytes
        bucket["up"] += r.up_bytes
        bucket["secs"] += r.seconds
    cycle = _cycle_start(cfg["billing_day"])
    online = bool(status and (utcnow() - status.updated_at).total_seconds() < 300
                  and not status.value.get("error") and status.value.get("state") in (None, "CONNECTED"))
    return {
        "enabled": cfg["enabled"],
        "online": online,
        "status": status.value if status else None,
        "updated_at": iso(status.updated_at) if status else None,
        "usage": {"today": usage(_local_midnight_utc()), "cycle": usage(cycle),
                  "cycle_start": cycle.replace(tzinfo=UTC).astimezone(LOCAL_TZ).date().isoformat()},
        "series": [{"t": iso(b["key"]), "latency_ms": sum(b["lat"]) / len(b["lat"]) if b["lat"] else None,
                    "down_bytes": b["down"], "up_bytes": b["up"]} for b in series],
    }
