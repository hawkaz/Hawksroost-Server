"""What the sky is doing now, as a weather icon + plain words.

Order of trust: what the station measures right now (rain, lightning), then
Tempest's own forecast "current conditions" when a token is set, then what
the station's sunlight says (measured vs what a clear sky would give at this
sun height). At night, without the forecast, we can't see clouds, so it just
says "Night" rather than guess.

Icon names follow Tempest's forecast names (clear-day, partly-cloudy-night,
rainy, thunderstorm, snow, …) so the app maps one set of names to icons.
"""
import math
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import WeatherEvent, WeatherObs

# Mormon Lake, AZ (used for the sun's position unless the forecast gives the station's own).
DEFAULT_LAT, DEFAULT_LON = 34.91, -111.46
WINDY_MS = 9.0          # about 20 mph average


def sun_elevation(lat: float, lon: float, when: datetime) -> float:
    """Sun height above the horizon in degrees (NOAA's approximation). `when` is UTC."""
    when = when.replace(tzinfo=UTC) if when.tzinfo is None else when.astimezone(UTC)
    doy = when.timetuple().tm_yday
    hour = when.hour + when.minute / 60 + when.second / 3600
    g = 2 * math.pi / 365 * (doy - 1 + (hour - 12) / 24)
    eqtime = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                       - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g)
            + 0.000907 * math.sin(2 * g) - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    tst = hour * 60 + eqtime + 4 * lon
    ha = math.radians(tst / 4 - 180)
    la = math.radians(lat)
    cos_zen = math.sin(la) * math.sin(decl) + math.cos(la) * math.cos(decl) * math.cos(ha)
    return 90 - math.degrees(math.acos(max(-1.0, min(1.0, cos_zen))))


def clear_sky_wm2(elevation_deg: float) -> float:
    """Sunlight a clear sky gives at this sun height (Haurwitz model), W/m²."""
    cz = math.sin(math.radians(elevation_deg))
    return 1098 * cz * math.exp(-0.057 / cz) if cz > 0.02 else 0.0


def decide(*, temp_c, raining: bool, lightning_km, wind_ms, solar_wm2, elevation: float,
           forecast_icon: str | None, forecast_words: str | None) -> dict:
    """Pure decision, easy to test."""
    day = elevation > 0
    if raining:
        if lightning_km is not None and lightning_km <= 20:
            return {"icon": "thunderstorm", "label": "Thunderstorm", "source": "station"}
        if temp_c is not None and temp_c <= 0.5:
            return {"icon": "snow", "label": "Snow", "source": "station"}
        return {"icon": "rainy", "label": "Rain", "source": "station"}
    if lightning_km is not None and lightning_km <= 20:
        return {"icon": "thunderstorm", "label": "Lightning nearby", "source": "station"}
    if forecast_icon:
        return {"icon": forecast_icon, "label": forecast_words or "", "source": "forecast"}
    windy = wind_ms is not None and wind_ms >= WINDY_MS
    if not day:
        return {"icon": "windy" if windy else "night", "label": "Windy night" if windy else "Night", "source": "station"}
    clear = clear_sky_wm2(elevation)
    ratio = (solar_wm2 or 0) / clear if clear else 0
    if ratio >= 0.75:
        icon, label = "clear-day", "Sunny"
    elif ratio >= 0.4:
        icon, label = "partly-cloudy-day", "Partly cloudy"
    else:
        icon, label = "cloudy", "Cloudy"
    if windy:
        label += " and windy"
    return {"icon": icon, "label": label, "source": "station"}


def now(db: Session, latest: dict | None, forecast: dict | None, wind_ms=None, at: datetime | None = None) -> dict | None:
    """Current condition from the latest reading, the last 10 minutes and the forecast."""
    if not latest:
        return None
    at = at or datetime.now(UTC).replace(tzinfo=None)
    since = at - timedelta(minutes=10)
    rain = db.scalar(select(func.coalesce(func.sum(WeatherObs.rain_mm), 0)).where(WeatherObs.ts >= since)) or 0
    solar = db.scalar(select(func.avg(WeatherObs.solar)).where(WeatherObs.ts >= since))
    near = db.scalar(select(func.min(WeatherEvent.distance_km)).where(
        WeatherEvent.kind == "strike", WeatherEvent.ts >= at - timedelta(minutes=30)))
    lat = (forecast or {}).get("latitude") or DEFAULT_LAT
    lon = (forecast or {}).get("longitude") or DEFAULT_LON
    return decide(
        temp_c=latest.get("temp_c"),
        raining=rain > 0 or (latest.get("rain_mm") or 0) > 0 or (latest.get("precip_type") or 0) > 0,
        lightning_km=near, wind_ms=wind_ms if wind_ms is not None else latest.get("wind_avg"),
        solar_wm2=solar if solar is not None else latest.get("solar"),
        elevation=sun_elevation(lat, lon, at),
        forecast_icon=(forecast or {}).get("icon"), forecast_words=(forecast or {}).get("conditions"))
