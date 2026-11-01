from datetime import datetime

from app.collector.starlink import rollup
from app.collector.tempest import parse_obs


def test_parse_obs():
    # Example obs_st values from the Tempest UDP docs.
    o = parse_obs([1588948614, 0.18, 0.22, 0.27, 144, 6, 1017.57, 22.37, 50.26, 328, 0.03, 3, 0.0, 0, 0, 0, 2.410, 1])
    assert o["temp_c"] == 22.37 and o["pressure_mb"] == 1017.57 and o["battery"] == 2.41
    assert o["ts"].year == 2020


def test_starlink_rollup_measures_minutes():
    n = 90
    drop = [0.0] * n
    drop[10] = drop[11] = 1.0   # two seconds with every ping lost
    bulk = {"pop_ping_latency_ms": [30.0] * n, "pop_ping_drop_rate": drop,
            "downlink_throughput_bps": [8000.0] * n, "uplink_throughput_bps": [800.0] * n,
            "power_w": [40.0] * n, "obstructed": [False] * n}
    rows = rollup(datetime(2026, 7, 1, 12, 0, 59), bulk, n)
    assert sum(r["seconds"] for r in rows) == n
    assert sum(r["outage_s"] for r in rows) == 2
    assert all(r["power_w"] == 40.0 and r["down_peak_bps"] == 8000.0 for r in rows)


def test_starlink_api_shapes(client):
    from app import state
    from app.db import SessionLocal
    from .conftest import login
    with SessionLocal() as db:
        state.put(db, "starlink_status", {"state": "CONNECTED", "alerts": ["is_heating", "brand_new_flag"]})
    login(client, "viewer")
    r = client.get("/api/starlink").json()
    assert r["online"] and r["state_label"] == "Online"
    assert [a["label"] for a in r["alerts"]] == ["Heating to melt snow", "Brand new flag"]
    assert client.get("/api/starlink/history").json()["series"] == []
    assert client.post("/api/admin/starlink/reboot").status_code == 403


def test_tempest_keeps_newest_reading():
    from app import state
    from app.collector.tempest import handle
    from app.db import SessionLocal

    def obs(t, temp):
        return {"type": "obs_st", "serial_number": "ST-1", "obs": [[t, 0, 1, 2, 90, 3, 800, temp, 40, 0, 0, 0, 0, 0, 0, 0, 2.6, 1]]}

    handle(obs(1_800_000_100, 10.0))
    handle(obs(1_800_000_000, 5.0))  # older packet arrives late
    with SessionLocal() as db:
        assert state.get(db, "tempest_obs")["temp_c"] == 10.0


def test_weather_history_ranges(client):
    from datetime import timedelta

    from app.db import SessionLocal
    from app.models import WeatherObs
    from app.timeutil import utcnow
    from .conftest import login
    now = utcnow()
    with SessionLocal() as db:
        for i in range(48):  # 4 hours at 5-minute steps
            db.add(WeatherObs(ts=now - timedelta(minutes=5 * i), temp_c=10 + i % 3, humidity=40, pressure_mb=780,
                              wind_avg=4, wind_lull=2, wind_gust=7, wind_dir=270, rain_mm=0.1 if i < 6 else 0))
        db.commit()
    login(client, "viewer")
    for period in ("day", "week", "month", "nonsense"):
        r = client.get(f"/api/weather/history?range={period}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["series"] and body["days"]
        rose = body["wind_rose"]
        assert rose["total"] == 48 and sum(rose["sectors"][12]) == 48   # all from the west
    assert abs(sum(p["rain_mm"] for p in body["series"]) - 0.6) < 1e-9
