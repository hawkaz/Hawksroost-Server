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
