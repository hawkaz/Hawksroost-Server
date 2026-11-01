"""FastAPI app. Run with a single worker: background jobs live in this process."""
import asyncio
import logging
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import select

from . import config, push
from .db import SessionLocal
from .models import TaskList
from .routers import admin, auth, calendar, cameras, lists, me, radio, starlink, today, weather
from .services import jobs, radio_files
from .services.cameras import CameraOffline, NotSupported
from .services.cameras import manager as camera_manager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("hawk")


def seed_defaults(db) -> None:
    """Starter lists on a brand-new install."""
    if db.scalar(select(TaskList.id).limit(1)) is None:
        db.add_all([TaskList(name="To-do", sort=1), TaskList(name="Before we leave", sort=2)])
        db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.ensure_dirs()
    with SessionLocal() as db:
        push.ensure_keys(db)
        seed_defaults(db)
    await camera_manager.start()
    tasks = [asyncio.create_task(jobs.daily_loop()), asyncio.create_task(radio_files.run())]
    yield
    for t in tasks:
        t.cancel()
    await camera_manager.stop()


app = FastAPI(title="Hawksroost", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@app.middleware("http")
async def same_origin(request: Request, call_next):
    """Block cross-site writes: a changing request must come from our own pages."""
    if request.method not in SAFE_METHODS and request.url.path.startswith("/api/"):
        origin = request.headers.get("origin")
        host = request.headers.get("x-forwarded-host") or request.headers.get("host")
        if origin and urlparse(origin).netloc != host:
            return JSONResponse({"detail": "Cross-site request blocked"}, status_code=403)
    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    msg = str(first.get("msg", "Check the form and try again.")).removeprefix("Value error, ")
    field = first.get("loc", [])[-1] if first.get("loc") else None
    return JSONResponse({"detail": msg, "field": field}, status_code=422)


@app.exception_handler(CameraOffline)
async def camera_offline(_: Request, __: CameraOffline):
    return JSONResponse({"detail": "That camera is offline right now."}, status_code=503)


@app.exception_handler(NotSupported)
async def not_supported(_: Request, __: NotSupported):
    return JSONResponse({"detail": "This camera can't do that."}, status_code=400)


@app.get("/api/ping")
def ping():
    return {"ok": True, "version": config.APP_VERSION}


for r in (auth, me, admin, calendar, lists, weather, starlink, cameras, today, radio):
    app.include_router(r.router)
