"""Home screen summary: who's at the cabin, what's open, weather, cameras."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import settings_store, state, users
from ..db import get_db
from ..deps import viewer
from ..models import Camera, Reservation, ShoppingItem, Task, TaskList, User
from ..services import sky
from .weather import cached_forecast
from ..timeutil import iso, local_today

router = APIRouter(tags=["today"])


@router.get("/api/today")
def today(db: Session = Depends(get_db), me: User = Depends(viewer)):
    d = local_today()
    here = db.scalars(select(Reservation).where(
        Reservation.kind == "stay", Reservation.start_date <= d, Reservation.end_date > d)).all()
    nxt = db.scalars(select(Reservation).where(Reservation.start_date > d)
                     .order_by(Reservation.start_date).limit(3)).all()
    people = {u.id: u for u in db.scalars(select(User))}
    open_tasks = db.execute(select(Task, TaskList.name).join(TaskList).where(Task.done_at.is_(None))
                            .order_by(Task.priority.desc(), Task.due_date.is_(None), Task.due_date, Task.created_at)
                            .limit(5)).all()
    task_count = db.scalar(select(func.count()).select_from(Task).where(Task.done_at.is_(None)))
    shop_count = db.scalar(select(func.count()).select_from(ShoppingItem).where(ShoppingItem.acquired_at.is_(None)))
    shop = db.scalars(select(ShoppingItem).where(ShoppingItem.acquired_at.is_(None))
                      .order_by(ShoppingItem.added_at.desc()).limit(5)).all()
    obs = state.get_row(db, "tempest_obs")
    sl = state.get_row(db, "starlink_status")
    cams = db.scalars(select(Camera).where(Camera.enabled).order_by(Camera.sort, Camera.id)).all()

    def booking(r: Reservation) -> dict:
        return {"id": r.id, "kind": r.kind, "title": r.title, "start_date": r.start_date.isoformat(),
                "end_date": r.end_date.isoformat(), "user": users.brief(r.user),
                "people": [users.brief(p) for p in r.people], "who": r.who()}

    return {
        "date": d.isoformat(),
        "at_cabin": [booking(r) for r in here],
        "next": [booking(r) for r in nxt],
        "tasks": [{"id": t.id, "title": t.title, "list": name, "priority": t.priority,
                   "assignee": users.brief(people.get(t.assignee_id)),
                   "due_date": t.due_date.isoformat() if t.due_date else None} for t, name in open_tasks],
        "task_count": task_count, "shopping_count": shop_count,
        "shopping": [{"id": i.id, "text": i.text, "qty": i.qty, "store": i.store} for i in shop],
        "units": settings_store.get(db, "general")["units"],
        "weather": {**obs.value, "updated_at": iso(obs.updated_at),
                    "condition": sky.now(db, obs.value, cached_forecast(db))} if obs else None,
        "starlink": {"state": sl.value.get("state"), "error": sl.value.get("error"),
                     "latency_ms": sl.value.get("latency_ms"), "updated_at": iso(sl.updated_at)} if sl else None,
        "cameras": [{"id": c.id, "name": c.name} for c in cams],
    }
