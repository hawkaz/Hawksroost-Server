"""Starlink dish poller.

The dish keeps ~15 minutes of per-second history. We poll every minute, take
only new samples (by counter), and roll them into one-minute rows, so data
usage is the sum of throughput × 1 s. It's approximate: gaps while the laptop
is off aren't counted, and it won't match Starlink's billing exactly.
"""
import asyncio
import logging
from datetime import UTC, datetime, timedelta

import starlink_grpc
from sqlalchemy.dialects.sqlite import insert

from .. import settings_store, state
from ..db import SessionLocal
from ..models import StarlinkSample

log = logging.getLogger("hawk.starlink")
POLL_S = 60


def _status(ctx) -> dict:
    status, obstruction, alerts = starlink_grpc.status_data(context=ctx)
    return {
        "state": status.get("state"),
        "uptime_s": status.get("uptime"),
        "latency_ms": status.get("pop_ping_latency_ms"),
        "drop_rate": status.get("pop_ping_drop_rate"),
        "down_bps": status.get("downlink_throughput_bps"),
        "up_bps": status.get("uplink_throughput_bps"),
        "fraction_obstructed": status.get("fraction_obstructed"),
        "currently_obstructed": status.get("currently_obstructed"),
        "software_version": status.get("software_version"),
        "alerts": [k for k, v in (alerts or {}).items() if v],
        "wedges": obstruction.get("wedges_fraction_obstructed[]"),
    }


def rollup(end: datetime, bulk: dict, samples: int) -> list[dict]:
    """Group per-second samples (last one at `end`) into minute rows."""
    rows: dict[datetime, dict] = {}
    for i in range(samples):
        t = end - timedelta(seconds=samples - 1 - i)
        minute = t.replace(second=0, microsecond=0)
        r = rows.setdefault(minute, {"ts": minute, "lat": [], "drop": [], "down": 0.0, "up": 0.0, "obs": 0, "n": 0})
        lat = bulk["pop_ping_latency_ms"][i]
        if lat is not None:
            r["lat"].append(lat)
        r["drop"].append(bulk["pop_ping_drop_rate"][i] or 0)
        r["down"] += (bulk["downlink_throughput_bps"][i] or 0) / 8
        r["up"] += (bulk["uplink_throughput_bps"][i] or 0) / 8
        r["obs"] += 1 if bulk["obstructed"][i] else 0
        r["n"] += 1
    out = []
    for r in rows.values():
        out.append({
            "ts": r["ts"], "latency_ms": sum(r["lat"]) / len(r["lat"]) if r["lat"] else None,
            "drop_rate": sum(r["drop"]) / len(r["drop"]), "down_bps": r["down"] * 8 / r["n"],
            "up_bps": r["up"] * 8 / r["n"], "down_bytes": r["down"], "up_bytes": r["up"],
            "obstructed_s": r["obs"], "seconds": r["n"],
        })
    return out


def _save(rows: list[dict]) -> None:
    with SessionLocal() as db:
        for r in rows:
            # A minute can be split across two polls: add to the existing row.
            stmt = insert(StarlinkSample).values(**r)
            stmt = stmt.on_conflict_do_update(index_elements=["ts"], set_={
                "down_bytes": StarlinkSample.down_bytes + stmt.excluded.down_bytes,
                "up_bytes": StarlinkSample.up_bytes + stmt.excluded.up_bytes,
                "obstructed_s": StarlinkSample.obstructed_s + stmt.excluded.obstructed_s,
                "seconds": StarlinkSample.seconds + stmt.excluded.seconds,
                "latency_ms": stmt.excluded.latency_ms, "drop_rate": stmt.excluded.drop_rate,
                "down_bps": stmt.excluded.down_bps, "up_bps": stmt.excluded.up_bps,
            })
            db.execute(stmt)
        db.commit()


async def run() -> None:
    ctx, address, counter = None, None, None
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
            general, bulk = await asyncio.to_thread(
                starlink_grpc.history_bulk_data, -1, counter, False, ctx)
            samples = general["samples"]
            if counter is not None and samples:
                # First poll after start only sets the counter: we can't tell
                # which of those samples were already counted before a restart.
                _save(rollup(datetime.now(UTC).replace(tzinfo=None, microsecond=0), bulk, samples))
            counter = general["end_counter"]
            with SessionLocal() as db:
                state.put(db, "starlink_status", status)
        except Exception as e:  # GrpcError, connection refused, etc.
            log.warning("Starlink poll failed: %s", e)
            with SessionLocal() as db:
                prev = state.get(db, "starlink_status") or {}
                state.put(db, "starlink_status", {**prev, "error": f"Can't reach the dish at {address}"})
            ctx = starlink_grpc.ChannelContext(target=address)
        await asyncio.sleep(POLL_S)
