from datetime import datetime

from app.collector.starlink import rollup
from app.collector.tempest import parse_obs


def test_parse_obs():
    # Example obs_st values from the Tempest UDP docs.
    o = parse_obs([1588948614, 0.18, 0.22, 0.27, 144, 6, 1017.57, 22.37, 50.26, 328, 0.03, 3, 0.0, 0, 0, 0, 2.410, 1])
    assert o["temp_c"] == 22.37 and o["pressure_mb"] == 1017.57 and o["battery"] == 2.41
    assert o["ts"].year == 2020


def test_starlink_rollup_sums_bytes():
    n = 90
    bulk = {"pop_ping_latency_ms": [30.0] * n, "pop_ping_drop_rate": [0.0] * n,
            "downlink_throughput_bps": [8000.0] * n, "uplink_throughput_bps": [800.0] * n,
            "obstructed": [False] * n}
    rows = rollup(datetime(2026, 7, 1, 12, 0, 59), bulk, n)
    assert sum(r["down_bytes"] for r in rows) == 1000 * n
    assert sum(r["seconds"] for r in rows) == n


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
