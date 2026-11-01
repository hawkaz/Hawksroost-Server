"""Cabin bookings. Overlapping stays are allowed but flagged."""
import logging
from datetime import date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from icalendar import Calendar, Event
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import push, settings_store, users
from ..db import SessionLocal, get_db
from ..deps import member, viewer
from ..models import Reservation, User
from ..security import can
from ..timeutil import iso
from ..web import base_url

log = logging.getLogger("hawk.calendar")
router = APIRouter(tags=["calendar"])


def overlaps(a: Reservation, b: Reservation) -> bool:
    """Stays overlap when they share a night. Departure day = next arrival day is fine."""
    return (a.id != b.id and a.kind == "stay" and b.kind == "stay"
            and a.start_date < b.end_date and b.start_date < a.end_date)


def _out(r: Reservation, conflicts: list[int]) -> dict:
    return {
        "id": r.id, "kind": r.kind, "title": r.title, "note": r.note,
        "start_date": r.start_date.isoformat(), "end_date": r.end_date.isoformat(),
        "user": users.brief(r.user), "people": [users.brief(p) for p in r.people], "others": r.others,
        "overlaps": conflicts,
        "created_at": iso(r.created_at), "updated_at": iso(r.updated_at),
    }


def _stays_near(db: Session, start: date, end: date) -> list[Reservation]:
    return list(db.scalars(select(Reservation).where(
        Reservation.kind == "stay", Reservation.start_date < end, Reservation.end_date > start)))


def _with_conflicts(db: Session, rows: list[Reservation]) -> list[dict]:
    if not rows:
        return []
    lo = min(r.start_date for r in rows)
    hi = max(r.end_date for r in rows) + timedelta(days=1)
    stays = _stays_near(db, lo, hi)
    return [_out(r, [s.id for s in stays if overlaps(r, s)]) for r in rows]


@router.get("/api/calendar")
def list_bookings(start: date, end: date, db: Session = Depends(get_db), _: User = Depends(viewer)):
    rows = db.scalars(select(Reservation).where(
        Reservation.start_date <= end, Reservation.end_date >= start
    ).order_by(Reservation.start_date, Reservation.id)).all()
    return _with_conflicts(db, list(rows))


@router.get("/api/calendar/upcoming")
def upcoming(limit: int = 5, db: Session = Depends(get_db), _: User = Depends(viewer)):
    today = date.today()
    rows = db.scalars(select(Reservation).where(Reservation.end_date >= today)
                      .order_by(Reservation.start_date).limit(limit)).all()
    return _with_conflicts(db, list(rows))


class BookingIn(BaseModel):
    kind: Literal["stay", "logistics"] = "stay"
    title: str = Field(min_length=1, max_length=120)
    start_date: date
    end_date: date | None = None
    note: str | None = Field(None, max_length=2000)
    people_ids: list[int] = Field(default_factory=list, max_length=50)   # who's coming (on the app)
    others: str | None = Field(None, max_length=200)                     # anyone else coming

    @model_validator(mode="after")
    def _dates(self):
        if self.kind == "logistics" or self.end_date is None:
            self.end_date = self.end_date or self.start_date
        if self.kind == "stay" and self.end_date <= self.start_date:
            raise ValueError("Leaving day has to be after arriving day.")
        if self.end_date < self.start_date:
            raise ValueError("End date is before start date.")
        if (self.end_date - self.start_date).days > 120:
            raise ValueError("That's more than 120 days.")
        return self


async def _notify_new_booking(booking_id: int, author_id: int) -> None:
    with SessionLocal() as db:
        r = db.get(Reservation, booking_id)
        if r is None or r.kind != "stay":
            return
        ids = [u.id for u in db.scalars(select(User).where(
            User.active, User.notify_bookings, User.id != author_id))
            if not push.is_muted(u)]
        when = f"{r.start_date:%b %-d} – {r.end_date:%b %-d}"
        try:
            await push.send_to_users(db, ids, f"{r.user.name} booked the cabin", f"{r.who()} · {r.title} · {when}",
                                     url=f"/calendar?date={r.start_date.isoformat()}", tag=f"booking-{r.id}")
        except Exception:
            log.exception("booking push failed")


@router.get("/api/calendar/people")
def people(db: Session = Depends(get_db), _: User = Depends(viewer)):
    """Everyone on the app, for "Who's coming"."""
    return [users.brief(u) for u in db.scalars(select(User).where(User.active).order_by(User.name))]


def _set_people(db: Session, r: Reservation, body: BookingIn) -> None:
    ids = set(body.people_ids)
    r.people = list(db.scalars(select(User).where(User.id.in_(ids), User.active))) if ids else []
    r.others = (body.others or "").strip() or None


@router.post("/api/calendar", status_code=201)
def create_booking(body: BookingIn, tasks: BackgroundTasks, db: Session = Depends(get_db), user: User = Depends(member)):
    r = Reservation(user_id=user.id, **body.model_dump(exclude={"people_ids", "others"}))
    _set_people(db, r, body)
    db.add(r)
    db.commit()
    db.refresh(r)
    tasks.add_task(_notify_new_booking, r.id, user.id)
    return _with_conflicts(db, [r])[0]


def _own(db: Session, booking_id: int, user: User) -> Reservation:
    r = db.get(Reservation, booking_id)
    if r is None:
        raise HTTPException(404, "That booking is gone.")
    if r.user_id != user.id and not can(user, "admin"):
        raise HTTPException(403, "Only the person who booked it (or an admin) can change it.")
    return r


@router.put("/api/calendar/{booking_id}")
def update_booking(booking_id: int, body: BookingIn, db: Session = Depends(get_db), user: User = Depends(member)):
    r = _own(db, booking_id, user)
    for k, v in body.model_dump(exclude={"people_ids", "others"}).items():
        setattr(r, k, v)
    _set_people(db, r, body)
    db.commit()
    return _with_conflicts(db, [r])[0]


@router.delete("/api/calendar/{booking_id}", status_code=204)
def delete_booking(booking_id: int, db: Session = Depends(get_db), user: User = Depends(member)):
    db.delete(_own(db, booking_id, user))
    db.commit()


@router.get("/api/calendar/feed")
def feed_url(request: Request, db: Session = Depends(get_db), user: User = Depends(viewer)):
    return {"url": f"{base_url(request, db)}/api/ical/{user.ical_token}.ics"}


@router.get("/api/ical/{token}.ics")
def ical(token: str, db: Session = Depends(get_db)):
    """Read-only calendar feed for phone calendars. The token in the URL is the key."""
    user = db.scalar(select(User).where(User.ical_token == token, User.active))
    if user is None:
        raise HTTPException(404)
    site = settings_store.get(db, "general")["site_name"]
    cal = Calendar()
    cal.add("prodid", f"-//{site}//cabin//EN")
    cal.add("version", "2.0")
    cal.add("x-wr-calname", f"{site} cabin")
    since = date.today() - timedelta(days=60)
    for r in db.scalars(select(Reservation).where(Reservation.end_date >= since)):
        ev = Event()
        ev.add("uid", f"booking-{r.id}@hawksroost")
        ev.add("summary", f"{r.who()}: {r.title}" if r.kind == "stay" else r.title)
        ev.add("dtstart", r.start_date)
        ev.add("dtend", r.end_date if r.kind == "stay" else r.end_date + timedelta(days=1))
        ev.add("dtstamp", r.updated_at or datetime.utcnow())
        if r.note:
            ev.add("description", r.note)
        cal.add_component(ev)
    return Response(cal.to_ical(), media_type="text/calendar")
