"""Weather icons: sun position and the rules that pick sunny / cloudy / rain / night."""
from datetime import datetime

from app.services.sky import clear_sky_wm2, decide, sun_elevation

LAT, LON = 34.91, -111.46


def test_sun_position_at_the_lake():
    noon_june = sun_elevation(LAT, LON, datetime(2026, 6, 21, 19, 30))      # 12:30 pm cabin time
    assert 75 < noon_june < 80
    noon_dec = sun_elevation(LAT, LON, datetime(2026, 12, 21, 19, 30))
    assert 28 < noon_dec < 34
    assert sun_elevation(LAT, LON, datetime(2026, 6, 21, 7, 0)) < 0          # midnight


def base(**kw):
    args = dict(temp_c=15, raining=False, lightning_km=None, wind_ms=2, solar_wm2=900, elevation=60,
                forecast_icon=None, forecast_words=None)
    args.update(kw)
    return decide(**args)


def test_station_rules():
    assert base()["icon"] == "clear-day"
    assert base(solar_wm2=clear_sky_wm2(60) * 0.5)["icon"] == "partly-cloudy-day"
    assert base(solar_wm2=80)["icon"] == "cloudy"
    assert base(elevation=-10) == {"icon": "night", "label": "Night", "source": "station"}
    assert base(raining=True)["icon"] == "rainy"
    assert base(raining=True, temp_c=0)["icon"] == "snow"
    assert base(raining=True, lightning_km=8)["icon"] == "thunderstorm"
    assert base(lightning_km=12)["label"] == "Lightning nearby"
    assert base(lightning_km=40)["icon"] == "clear-day"           # far-off strikes don't count
    assert base(wind_ms=12)["label"] == "Sunny and windy"


def test_forecast_used_unless_the_station_sees_otherwise():
    f = dict(forecast_icon="partly-cloudy-night", forecast_words="Partly Cloudy")
    assert base(elevation=-5, **f) == {"icon": "partly-cloudy-night", "label": "Partly Cloudy", "source": "forecast"}
    assert base(raining=True, **f)["icon"] == "rainy"             # rain on the gauge wins
