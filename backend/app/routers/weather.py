"""Tempest weather. Values are metric; the browser converts for display."""
import logging
import math
import time
from datetime import UTC, datetime, timedelta

import httpx
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import settings_store, state
from ..db import get_db
from ..deps import viewer
from ..models import WeatherEvent, WeatherObs
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


# --- Derived values (standard formulas; inputs are what the station measured) ---------------

def dew_point_c(t: float | None, rh: float | None) -> float | None:
    """Magnus formula."""
    if t is None or not rh:
        return None
    a, b = 17.62, 243.12
    g = math.log(rh / 100) + a * t / (b + t)
    return b * g / (a - g)


def feels_like_c(t: float | None, rh: float | None, wind_ms: float | None) -> float | None:
    """NWS heat index when hot and humid, wind chill when cold and breezy, else the air temperature."""
    if t is None:
        return None
    f = t * 9 / 5 + 32
    mph = (wind_ms or 0) * 2.23694
    if f >= 80 and (rh or 0) >= 40:
        r = rh
        hi = (-42.379 + 2.04901523 * f + 10.14333127 * r - 0.22475541 * f * r - 6.83783e-3 * f * f
              - 5.481717e-2 * r * r + 1.22874e-3 * f * f * r + 8.5282e-4 * f * r * r - 1.99e-6 * f * f * r * r)
        return (hi - 32) * 5 / 9
    if f <= 50 and mph > 3:
        wc = 35.74 + 0.6215 * f - 35.75 * mph ** 0.16 + 0.4275 * f * mph ** 0.16
        return (wc - 32) * 5 / 9
    return t


def sea_level_mb(station_mb: float | None, temp_c: float | None, elevation_m: float) -> float | None:
    if station_mb is None or not elevation_m:
        return station_mb
    t = temp_c if temp_c is not None else 15
    return station_mb * (1 - 0.0065 * elevation_m / (t + 0.0065 * elevation_m + 273.15)) ** -5.257


def _elevation_m(cfg: dict) -> float:
    return float(cfg.get("elevation_ft") or 0) * 0.3048


def _range_sum(db: Session, col, start: datetime, end: datetime | None = None) -> float:
    q = select(func.coalesce(func.sum(col), 0)).where(WeatherObs.ts >= start)
    if end is not None:
        q = q.where(WeatherObs.ts < end)
    return db.scalar(q) or 0


@router.get("/api/weather")
async def weather_now(db: Session = Depends(get_db)):
    cfg = settings_store.get(db, "tempest")
    elev = _elevation_m(cfg)
    obs = state.get_row(db, "tempest_obs")
    wind = state.get(db, "tempest_wind")
    now_utc = utcnow()
    midnight = _local_midnight_utc()
    n = dict(obs.value) if obs else None
    derived = {}
    if n:
        t, rh = n.get("temp_c"), n.get("humidity")
        derived = {
            "dew_point_c": dew_point_c(t, rh),
            "feels_like_c": feels_like_c(t, rh, (wind or {}).get("speed", n.get("wind_avg"))),
            "pressure_mb": sea_level_mb(n.get("pressure_mb"), t, elev),
            "pressure_kind": "sea level" if elev else "station",
            "rain_rate_mm_h": (n.get("rain_mm") or 0) * 60,
        }
        past = db.scalar(select(WeatherObs).where(WeatherObs.ts <= now_utc - timedelta(hours=3))
                         .order_by(WeatherObs.ts.desc()).limit(1))
        if past and past.pressure_mb and n.get("pressure_mb") and (now_utc - past.ts) < timedelta(hours=4):
            delta = n["pressure_mb"] - past.pressure_mb
            derived["pressure_trend"] = {"delta_mb": delta,
                                         "word": "rising" if delta > 1 else "falling" if delta < -1 else "steady"}
    hi = db.scalar(select(WeatherObs).where(WeatherObs.ts >= midnight, WeatherObs.temp_c.is_not(None))
                   .order_by(WeatherObs.temp_c.desc()).limit(1))
    lo = db.scalar(select(WeatherObs).where(WeatherObs.ts >= midnight, WeatherObs.temp_c.is_not(None))
                   .order_by(WeatherObs.temp_c.asc()).limit(1))
    gust = db.scalar(select(WeatherObs).where(WeatherObs.ts >= midnight, WeatherObs.wind_gust.is_not(None))
                     .order_by(WeatherObs.wind_gust.desc()).limit(1))
    strikes3 = db.execute(select(func.count(), func.min(WeatherEvent.distance_km), func.max(WeatherEvent.ts))
                          .where(WeatherEvent.kind == "strike", WeatherEvent.ts >= now_utc - timedelta(hours=3))).one()
    strikes24 = db.scalar(select(func.count()).select_from(WeatherEvent).where(
        WeatherEvent.kind == "strike", WeatherEvent.ts >= now_utc - timedelta(hours=24)))
    return {
        "enabled": cfg["enabled"],
        "units": settings_store.get(db, "general")["units"],
        "now": n,
        "derived": derived,
        "updated_at": iso(obs.updated_at) if obs else None,
        "wind": wind,
        "today": {
            "high_c": hi.temp_c if hi else None, "high_at": iso(hi.ts) if hi else None,
            "low_c": lo.temp_c if lo else None, "low_at": iso(lo.ts) if lo else None,
            "gust_max_ms": gust.wind_gust if gust else None, "gust_at": iso(gust.ts) if gust else None,
        },
        "rain": {
            "today_mm": _range_sum(db, WeatherObs.rain_mm, midnight),
            "yesterday_mm": _range_sum(db, WeatherObs.rain_mm, _local_midnight_utc(1), midnight),
            "last_24h_mm": _range_sum(db, WeatherObs.rain_mm, now_utc - timedelta(hours=24)),
            "last_7d_mm": _range_sum(db, WeatherObs.rain_mm, now_utc - timedelta(days=7)),
        },
        "lightning": {"count_3h": strikes3[0], "nearest_km": strikes3[1], "last": iso(strikes3[2]),
                      "count_24h": strikes24},
        "forecast": await _forecast(cfg),
    }


# Bucket sizes: 15 minutes over a day, 2 hours over a week (shows each day's cycle),
# one cabin day over a month (low–high band per day reads better than 120 zigzags).
RANGES = {"day": (24, 15 * 60), "week": (24 * 7, 2 * 3600), "month": (24 * 30, 24 * 3600)}
WIND_CLASSES_MS = (3.0, 6.0, 10.0)  # boundaries for the wind rose (about 7, 13, 22 mph)


def _local_bucket(ts: datetime, size_s: int) -> int:
    """Bucket start (UTC epoch) aligned to local clock boundaries (e.g. 6 am, noon)."""
    aware = ts.replace(tzinfo=UTC)
    off = int(aware.astimezone(LOCAL_TZ).utcoffset().total_seconds())
    epoch = int(aware.timestamp())
    return (epoch + off) // size_s * size_s - off


@router.get("/api/weather/history")
def weather_history(period: str = Query("day", alias="range"), db: Session = Depends(get_db)):
    hours, size = RANGES.get(period, RANGES["day"])
    cfg = settings_store.get(db, "tempest")
    elev = _elevation_m(cfg)
    since = utcnow() - timedelta(hours=hours)
    rows = db.scalars(select(WeatherObs).where(WeatherObs.ts >= since).order_by(WeatherObs.ts)).all()

    buckets: dict[int, dict] = {}
    days: dict[str, dict] = {}
    rose = [[0] * (len(WIND_CLASSES_MS) + 1) for _ in range(16)]
    calm = 0
    for r in rows:
        b = buckets.setdefault(_local_bucket(r.ts, size), {
            "t": [], "hum": [], "p": [], "w": [], "lull": None, "gust": None, "u": 0.0, "v": 0.0,
            "rain": 0.0, "solar": [], "uv": None})
        if r.temp_c is not None:
            b["t"].append(r.temp_c)
        if r.humidity is not None:
            b["hum"].append(r.humidity)
        if r.pressure_mb:
            b["p"].append(sea_level_mb(r.pressure_mb, r.temp_c, elev))
        if r.wind_avg is not None:
            b["w"].append(r.wind_avg)
            if r.wind_dir is not None and r.wind_avg > 0:
                rad = math.radians(r.wind_dir)
                b["u"] += r.wind_avg * math.sin(rad)
                b["v"] += r.wind_avg * math.cos(rad)
            if r.wind_avg < 0.5 or r.wind_dir is None:
                calm += 1
            else:
                cls = sum(r.wind_avg >= c for c in WIND_CLASSES_MS)
                rose[int(((r.wind_dir + 11.25) % 360) // 22.5)][cls] += 1
        if r.wind_lull is not None:
            b["lull"] = r.wind_lull if b["lull"] is None else min(b["lull"], r.wind_lull)
        if r.wind_gust is not None:
            b["gust"] = r.wind_gust if b["gust"] is None else max(b["gust"], r.wind_gust)
        b["rain"] += r.rain_mm or 0
        if r.solar is not None:
            b["solar"].append(r.solar)
        if r.uv is not None:
            b["uv"] = r.uv if b["uv"] is None else max(b["uv"], r.uv)
        day = r.ts.replace(tzinfo=UTC).astimezone(LOCAL_TZ).date().isoformat()
        d = days.setdefault(day, {"date": day, "high_c": None, "low_c": None, "rain_mm": 0.0, "gust_ms": None})
        if r.temp_c is not None:
            d["high_c"] = r.temp_c if d["high_c"] is None else max(d["high_c"], r.temp_c)
            d["low_c"] = r.temp_c if d["low_c"] is None else min(d["low_c"], r.temp_c)
        d["rain_mm"] += r.rain_mm or 0
        if r.wind_gust is not None:
            d["gust_ms"] = r.wind_gust if d["gust_ms"] is None else max(d["gust_ms"], r.wind_gust)

    def avg(xs):
        return sum(xs) / len(xs) if xs else None

    series = []
    for k, b in sorted(buckets.items()):
        series.append({
            "t": datetime.fromtimestamp(k, UTC).isoformat().replace("+00:00", "Z"),
            "temp_c": avg(b["t"]), "temp_min_c": min(b["t"]) if b["t"] else None,
            "temp_max_c": max(b["t"]) if b["t"] else None,
            "humidity": avg(b["hum"]), "pressure_mb": avg(b["p"]),
            "wind_avg": avg(b["w"]), "wind_lull": b["lull"], "wind_gust": b["gust"],
            "wind_dir": (math.degrees(math.atan2(b["u"], b["v"])) % 360) if (b["u"] or b["v"]) else None,
            "rain_mm": b["rain"], "solar": avg(b["solar"]), "uv": b["uv"],
        })
    total_wind = sum(map(sum, rose)) + calm
    strikes = db.scalars(select(WeatherEvent).where(WeatherEvent.kind == "strike", WeatherEvent.ts >= since)
                         .order_by(WeatherEvent.ts.desc()).limit(500)).all()
    return {
        "range": period if period in RANGES else "day", "bucket_s": size, "since": iso(since), "series": series,
        "pressure_kind": "sea level" if elev else "station",
        "days": sorted(days.values(), key=lambda d: d["date"]),
        "wind_rose": {"classes_ms": WIND_CLASSES_MS, "sectors": rose, "calm": calm, "total": total_wind},
        "strikes": [{"t": iso(s.ts), "distance_km": s.distance_km} for s in strikes],
    }
