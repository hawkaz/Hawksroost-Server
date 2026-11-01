"""Starlink dish poller.

Everything here is what the dish itself reports over its local gRPC API — no
estimates. Every minute: current status and alerts, the dish's own statistics
over its ~15-minute history buffer, and one-minute rollups of that per-second
history (latency, ping drop, throughput, power, obstructed and outage seconds).
Every ten minutes: the sky obstruction map and the sleep schedule.
"""
import asyncio
import base64
import logging
import time
from datetime import UTC, datetime, timedelta

import starlink_grpc
from sqlalchemy import case, func
from sqlalchemy.dialects.sqlite import insert

from .. import settings_store, state
from ..db import SessionLocal
from ..models import StarlinkSample

log = logging.getLogger("hawk.starlink")
POLL_S = 60
SLOW_EVERY_S = 600
LIVE_STEP_S = 5           # live charts: one point per 5 s over the last 15 minutes


def _status(ctx) -> dict:
    status, obstruction, alerts = starlink_grpc.status_data(context=ctx)
    return {
        "id": status.get("id"),
        "state": status.get("state"),
        "uptime_s": status.get("uptime"),
        "hardware_version": status.get("hardware_version"),
        "software_version": status.get("software_version"),
        "latency_ms": status.get("pop_ping_latency_ms"),
        "drop_rate": status.get("pop_ping_drop_rate"),
        "down_bps": status.get("downlink_throughput_bps"),
        "up_bps": status.get("uplink_throughput_bps"),
        "seconds_to_first_slot": status.get("seconds_to_first_nonempty_slot"),
        "snr_ok": status.get("is_snr_above_noise_floor"),
        "fraction_obstructed": status.get("fraction_obstructed"),
        "currently_obstructed": status.get("currently_obstructed"),
        "obstruction_duration_s": status.get("obstruction_duration"),
        "obstruction_interval_s": status.get("obstruction_interval"),
        "obstruction_valid_s": obstruction.get("valid_s"),
        "azimuth": status.get("direction_azimuth"),
        "elevation": status.get("direction_elevation"),
        "gps_ready": status.get("gps_ready"),
        "gps_enabled": status.get("gps_enabled"),
        "gps_sats": status.get("gps_sats"),
        "alerts": sorted(k.removeprefix("alert_") for k, v in (alerts or {}).items() if v),
    }


def _stats(ctx, history) -> dict:
    """The dish's own statistics over its history buffer (~15 minutes)."""
    general, drop, drop_runs, latency, loaded, _usage, power = starlink_grpc.history_stats(
        -1, context=ctx, history=history)
    return {
        "samples": general.get("samples"),
        "total_ping_drop": drop.get("total_ping_drop"),
        "full_drop_s": drop.get("count_full_ping_drop"),
        "obstructed_s": drop.get("count_obstructed"),
        "unscheduled_s": drop.get("count_unscheduled"),
        "latency_mean": latency.get("mean_all_ping_latency"),
        "latency_deciles": latency.get("deciles_all_ping_latency[]"),
        "latency_stdev": latency.get("stdev_full_ping_latency"),
        "loaded_samples": loaded.get("load_bucket_samples[]"),
        "loaded_min": loaded.get("load_bucket_min_latency[]"),
        "loaded_median": loaded.get("load_bucket_median_latency[]"),
        "loaded_max": loaded.get("load_bucket_max_latency[]"),
        "outage_runs_s": drop_runs.get("run_seconds[1,]"),
        "power_latest": power.get("latest_power"),
        "power_mean": power.get("mean_power"),
        "power_min": power.get("min_power"),
        "power_max": power.get("max_power"),
    }


def _live(bulk: dict, samples: int, end: datetime) -> dict:
    """Last 15 minutes at 5-second resolution for the live charts."""
    pts = []
    for start in range(0, samples, LIVE_STEP_S):
        idx = range(start, min(start + LIVE_STEP_S, samples))
        lat = [bulk["pop_ping_latency_ms"][i] for i in idx if bulk["pop_ping_latency_ms"][i] is not None]
        t = end - timedelta(seconds=samples - 1 - idx[-1])
        pts.append({
            "t": t.isoformat() + "Z",
            "latency_ms": sum(lat) / len(lat) if lat else None,
            "drop": sum(bulk["pop_ping_drop_rate"][i] or 0 for i in idx) / len(idx),
            "down_bps": max(bulk["downlink_throughput_bps"][i] or 0 for i in idx),
            "up_bps": max(bulk["uplink_throughput_bps"][i] or 0 for i in idx),
            "power_w": (sum(bulk["power_w"][i] or 0 for i in idx) / len(idx)) if "power_w" in bulk else None,
            "obstructed": any(bulk["obstructed"][i] for i in idx),
        })
    return {"step_s": LIVE_STEP_S, "points": pts}


def rollup(end: datetime, bulk: dict, samples: int) -> list[dict]:
    """Group per-second samples (last one at `end`) into one-minute rows."""
    rows: dict[datetime, dict] = {}
    for i in range(samples):
        t = end - timedelta(seconds=samples - 1 - i)
        minute = t.replace(second=0, microsecond=0)
        r = rows.setdefault(minute, {"lat": [], "drop": [], "down": [], "up": [], "power": [], "obs": 0, "out": 0})
        lat = bulk["pop_ping_latency_ms"][i]
        if lat is not None:
            r["lat"].append(lat)
        drop = bulk["pop_ping_drop_rate"][i] or 0
        r["drop"].append(drop)
        r["out"] += 1 if drop >= 1 else 0
        r["down"].append(bulk["downlink_throughput_bps"][i] or 0)
        r["up"].append(bulk["uplink_throughput_bps"][i] or 0)
        if bulk.get("power_w") and bulk["power_w"][i] is not None:
            r["power"].append(bulk["power_w"][i])
        r["obs"] += 1 if bulk["obstructed"][i] else 0
    out = []
    for minute, r in rows.items():
        n = len(r["drop"])
        out.append({
            "ts": minute,
            "latency_ms": sum(r["lat"]) / len(r["lat"]) if r["lat"] else None,
            "drop_rate": sum(r["drop"]) / n,
            "down_bps": sum(r["down"]) / n, "up_bps": sum(r["up"]) / n,
            "down_peak_bps": max(r["down"]), "up_peak_bps": max(r["up"]),
            "power_w": sum(r["power"]) / len(r["power"]) if r["power"] else None,
            "obstructed_s": r["obs"], "outage_s": r["out"], "seconds": n,
        })
    return out


def _save(rows: list[dict]) -> None:
    with SessionLocal() as db:
        for r in rows:
            # A minute can be split across two polls: merge into the existing row. Averages
            # are weighted by the seconds each part covers; peaks keep the higher one.
            stmt = insert(StarlinkSample).values(**r)
            old, new = StarlinkSample, stmt.excluded
            total = old.seconds + new.seconds

            def avg(col: str):
                a, b = getattr(old, col), getattr(new, col)
                return case((a.is_(None), b), (b.is_(None), a),
                            else_=(a * old.seconds + b * new.seconds) / func.max(total, 1))

            def peak(col: str):
                return func.max(func.coalesce(getattr(old, col), 0), func.coalesce(getattr(new, col), 0))

            stmt = stmt.on_conflict_do_update(index_elements=["ts"], set_={
                **{c: avg(c) for c in ("latency_ms", "drop_rate", "down_bps", "up_bps", "power_w")},
                "down_peak_bps": peak("down_peak_bps"), "up_peak_bps": peak("up_peak_bps"),
                "obstructed_s": old.obstructed_s + new.obstructed_s,
                "outage_s": old.outage_s + new.outage_s,
                "seconds": total,
            })
            db.execute(stmt)
        db.commit()


def _map(ctx) -> dict | None:
    """Sky obstruction map, packed: 0 = no data, 1..255 = signal quality 0..1."""
    rows = starlink_grpc.obstruction_map(context=ctx)
    if not rows or not rows[0]:
        return None
    packed = bytearray()
    for row in rows:
        for v in row:
            packed.append(0 if v < 0 else 1 + round(min(v, 1.0) * 254))
    return {"rows": len(rows), "cols": len(rows[0]), "data": base64.b64encode(bytes(packed)).decode()}


def _sleep(ctx) -> dict | None:
    start, duration, enabled = starlink_grpc.get_sleep_config(context=ctx)
    return {"start_utc_min": start, "duration_min": duration, "enabled": enabled}


async def run() -> None:
    ctx, address, counter, last_slow = None, None, None, 0.0
    while True:
        with SessionLocal() as db:
            cfg = settings_store.get(db, "starlink")
        if not cfg["enabled"]:
            await asyncio.sleep(POLL_S)
            continue
        if cfg["address"] != address:
            address, counter = cfg["address"], None
            ctx = starlink_grpc.ChannelContext(target=address)
        try:
            status = await asyncio.to_thread(_status, ctx)
            history = await asyncio.to_thread(starlink_grpc.get_history, ctx)
            general, bulk = await asyncio.to_thread(starlink_grpc.history_bulk_data, -1, counter, False, ctx, history)
            now = datetime.now(UTC).replace(tzinfo=None, microsecond=0)
            if counter is not None and general["samples"]:
                # First poll after start only sets the counter: earlier samples
                # may already have been saved before a restart.
                _save(rollup(now, bulk, general["samples"]))
            counter = general["end_counter"]
            _, full = await asyncio.to_thread(starlink_grpc.history_bulk_data, 900, None, False, ctx, history)
            stats = await asyncio.to_thread(_stats, ctx, history)
            with SessionLocal() as db:
                state.put(db, "starlink_status", status, commit=False)
                state.put(db, "starlink_stats", stats, commit=False)
                state.put(db, "starlink_live", _live(full, len(full["pop_ping_latency_ms"]), now))
            if time.monotonic() - last_slow > SLOW_EVERY_S:
                last_slow = time.monotonic()
                for key, fn in (("starlink_map", _map), ("starlink_sleep", _sleep)):
                    try:
                        value = await asyncio.to_thread(fn, ctx)
                        if value is not None:
                            with SessionLocal() as db:
                                state.put(db, key, value)
                    except Exception as e:  # older firmware may not support every call
                        log.info("Starlink %s unavailable: %s", key, e)
        except Exception as e:  # GrpcError, connection refused, etc.
            log.warning("Starlink poll failed: %s", e)
            with SessionLocal() as db:
                prev = state.get(db, "starlink_status") or {}
                state.put(db, "starlink_status", {**prev, "error": f"Can't reach the dish at {address}"})
            ctx = starlink_grpc.ChannelContext(target=address)
        await asyncio.sleep(POLL_S)
