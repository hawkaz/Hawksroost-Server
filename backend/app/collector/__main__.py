"""Collector process: Tempest UDP + Starlink polling.

Runs in its own container on the host network, because Tempest broadcasts UDP
on the LAN and Docker's port publishing doesn't reliably pass broadcasts.
"""
import asyncio
import logging
import os

from .. import config, state
from ..db import SessionLocal
from . import starlink, tempest

log = logging.getLogger("hawk.collector")


async def heartbeat() -> None:
    while True:
        with SessionLocal() as db:
            state.put(db, "collector", {"pid": os.getpid()})
        await asyncio.sleep(30)


async def supervise(name, fn) -> None:
    """Keep a job alive: log and restart after a crash."""
    while True:
        try:
            await fn()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("%s crashed; restarting in 30 s", name)
            await asyncio.sleep(30)


async def main() -> None:
    config.ensure_dirs()
    await asyncio.gather(
        supervise("heartbeat", heartbeat),
        supervise("tempest", tempest.run),
        supervise("starlink", starlink.run),
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    asyncio.run(main())
