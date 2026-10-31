"""Small live-state values shared between the collector and the API (kv_state table)."""
from sqlalchemy.orm import Session

from .models import KeyValue
from .timeutil import utcnow


def get_row(db: Session, key: str) -> KeyValue | None:
    return db.get(KeyValue, key)


def get(db: Session, key: str) -> dict | None:
    row = db.get(KeyValue, key)
    return row.value if row else None


def put(db: Session, key: str, value: dict, commit: bool = True) -> None:
    row = db.get(KeyValue, key)
    if row is None:
        db.add(KeyValue(key=key, value=value, updated_at=utcnow()))
    else:
        row.value = value
        row.updated_at = utcnow()
    if commit:
        db.commit()
