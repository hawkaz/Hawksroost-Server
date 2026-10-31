"""Shopping list and to-do lists. Every add/complete records who and when."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .. import users
from ..db import get_db
from ..deps import member, viewer
from ..models import ShoppingItem, Task, TaskList, User
from ..timeutil import iso, utcnow

router = APIRouter(prefix="/api/lists", tags=["lists"])


def _people(db: Session) -> dict[int, User]:
    return {u.id: u for u in db.scalars(select(User))}


# --- Shopping ------------------------------------------------------------------------

def _item(i: ShoppingItem, people: dict[int, User]) -> dict:
    return {
        "id": i.id, "text": i.text, "qty": i.qty, "store": i.store,
        "added_by": users.brief(people.get(i.added_by)), "added_at": iso(i.added_at),
        "acquired_by": users.brief(people.get(i.acquired_by)), "acquired_at": iso(i.acquired_at),
    }


@router.get("/shopping")
def shopping(history_days: int = 14, db: Session = Depends(get_db), _: User = Depends(viewer)):
    people = _people(db)
    open_items = db.scalars(select(ShoppingItem).where(ShoppingItem.acquired_at.is_(None))
                            .order_by(ShoppingItem.store, ShoppingItem.added_at)).all()
    since = utcnow() - timedelta(days=history_days)
    got = db.scalars(select(ShoppingItem).where(ShoppingItem.acquired_at >= since)
                     .order_by(ShoppingItem.acquired_at.desc()).limit(100)).all()
    stores = [s for (s,) in db.execute(select(ShoppingItem.store).where(ShoppingItem.store.is_not(None))
                                       .group_by(ShoppingItem.store).order_by(func.count().desc()).limit(12))]
    return {"open": [_item(i, people) for i in open_items],
            "acquired": [_item(i, people) for i in got], "stores": stores}


class ItemIn(BaseModel):
    text: str = Field(min_length=1, max_length=200)
    qty: str | None = Field(None, max_length=40)
    store: str | None = Field(None, max_length=60)


@router.post("/shopping", status_code=201)
def add_item(body: ItemIn, db: Session = Depends(get_db), user: User = Depends(member)):
    i = ShoppingItem(text=body.text.strip(), qty=(body.qty or "").strip() or None,
                     store=(body.store or "").strip() or None, added_by=user.id)
    db.add(i)
    db.commit()
    return _item(i, _people(db))


class ItemPatch(BaseModel):
    text: str | None = Field(None, min_length=1, max_length=200)
    qty: str | None = Field(None, max_length=40)
    store: str | None = Field(None, max_length=60)
    acquired: bool | None = None


@router.patch("/shopping/{item_id}")
def update_item(item_id: int, body: ItemPatch, db: Session = Depends(get_db), user: User = Depends(member)):
    i = db.get(ShoppingItem, item_id) or _404()
    data = body.model_dump(exclude_unset=True)
    acquired = data.pop("acquired", None)
    for k, v in data.items():
        setattr(i, k, (v or "").strip() or None if k != "text" else v.strip())
    if acquired is True and i.acquired_at is None:
        i.acquired_at, i.acquired_by = utcnow(), user.id
    elif acquired is False:
        i.acquired_at = i.acquired_by = None
    db.commit()
    return _item(i, _people(db))


@router.delete("/shopping/{item_id}", status_code=204)
def delete_item(item_id: int, db: Session = Depends(get_db), _: User = Depends(member)):
    db.delete(db.get(ShoppingItem, item_id) or _404())
    db.commit()


# --- To-do lists ---------------------------------------------------------------------

def _task(t: Task, people: dict[int, User]) -> dict:
    return {
        "id": t.id, "list_id": t.list_id, "title": t.title, "notes": t.notes, "priority": t.priority,
        "due_date": t.due_date.isoformat() if t.due_date else None,
        "assignee": users.brief(people.get(t.assignee_id)),
        "created_by": users.brief(people.get(t.created_by)), "created_at": iso(t.created_at),
        "done_by": users.brief(people.get(t.done_by)), "done_at": iso(t.done_at),
    }


@router.get("/tasks")
def task_lists(history_days: int = 30, db: Session = Depends(get_db), _: User = Depends(viewer)):
    people = _people(db)
    since = utcnow() - timedelta(days=history_days)
    lists = db.scalars(select(TaskList).order_by(TaskList.sort, TaskList.id)).all()
    tasks = db.scalars(select(Task).where((Task.done_at.is_(None)) | (Task.done_at >= since))
                       .order_by(Task.done_at.is_not(None), Task.priority.desc(), Task.created_at)).all()
    by_list: dict[int, list] = {}
    for t in tasks:
        by_list.setdefault(t.list_id, []).append(_task(t, people))
    return [{"id": l.id, "name": l.name, "tasks": by_list.get(l.id, [])} for l in lists]


class ListIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


@router.post("/tasks", status_code=201)
def create_list(body: ListIn, db: Session = Depends(get_db), _: User = Depends(member)):
    sort = (db.scalar(select(func.max(TaskList.sort))) or 0) + 1
    l = TaskList(name=body.name.strip(), sort=sort)
    db.add(l)
    db.commit()
    return {"id": l.id, "name": l.name, "tasks": []}


@router.patch("/tasks/{list_id}")
def rename_list(list_id: int, body: ListIn, db: Session = Depends(get_db), _: User = Depends(member)):
    l = db.get(TaskList, list_id) or _404()
    l.name = body.name.strip()
    db.commit()
    return {"id": l.id, "name": l.name}


@router.delete("/tasks/{list_id}", status_code=204)
def delete_list(list_id: int, db: Session = Depends(get_db), _: User = Depends(member)):
    db.delete(db.get(TaskList, list_id) or _404())
    db.commit()


@router.post("/tasks/{list_id}/reset", status_code=204)
def reset_list(list_id: int, db: Session = Depends(get_db), _: User = Depends(member)):
    """Untick everything — for repeat checklists like "Before we leave"."""
    db.execute(update(Task).where(Task.list_id == list_id).values(done_at=None, done_by=None))
    db.commit()


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    notes: str | None = Field(None, max_length=4000)
    priority: int = Field(1, ge=0, le=2)
    assignee_id: int | None = None
    due_date: date | None = None


@router.post("/tasks/{list_id}/items", status_code=201)
def add_task(list_id: int, body: TaskIn, db: Session = Depends(get_db), user: User = Depends(member)):
    db.get(TaskList, list_id) or _404()
    t = Task(list_id=list_id, created_by=user.id, **body.model_dump())
    t.title = t.title.strip()
    db.add(t)
    db.commit()
    return _task(t, _people(db))


class TaskPatch(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    notes: str | None = Field(None, max_length=4000)
    priority: int | None = Field(None, ge=0, le=2)
    assignee_id: int | None = None
    due_date: date | None = None
    list_id: int | None = None
    done: bool | None = None


@router.patch("/tasks/items/{task_id}")
def update_task(task_id: int, body: TaskPatch, db: Session = Depends(get_db), user: User = Depends(member)):
    t = db.get(Task, task_id) or _404()
    data = body.model_dump(exclude_unset=True)
    done = data.pop("done", None)
    if "list_id" in data and data["list_id"] is not None:
        db.get(TaskList, data["list_id"]) or _404()
    for k, v in data.items():
        if k == "list_id" and v is None:
            continue
        setattr(t, k, v)
    if done is True and t.done_at is None:
        t.done_at, t.done_by = utcnow(), user.id
    elif done is False:
        t.done_at = t.done_by = None
    db.commit()
    return _task(t, _people(db))


@router.delete("/tasks/items/{task_id}", status_code=204)
def delete_task(task_id: int, db: Session = Depends(get_db), _: User = Depends(member)):
    db.delete(db.get(Task, task_id) or _404())
    db.commit()


def _404():
    raise HTTPException(404, "That's gone — someone may have just removed it.")
