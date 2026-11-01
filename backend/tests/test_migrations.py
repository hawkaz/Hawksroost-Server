"""The migrations themselves: they build the same database as the models, and changing
a table never deletes the rows that point at it."""
from datetime import date
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from app.db import Base, SessionLocal, engine, foreign_keys_off
from app.models import Reservation
from app.users import create_user

BACKEND = Path(__file__).resolve().parents[1]


def _alembic() -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    return cfg


def _empty_database():
    Base.metadata.drop_all(engine)
    with engine.begin() as c:
        c.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")


def test_migrations_match_the_models():
    _empty_database()
    cfg = _alembic()
    command.upgrade(cfg, "head")
    command.check(cfg)   # raises if the models have changes no migration makes


def test_rebuilding_a_table_keeps_rows_that_point_at_it():
    _empty_database()
    command.upgrade(_alembic(), "head")
    with SessionLocal() as db:
        ann = create_user(db, "Ann", "ann@example.com", "member")
        db.add(Reservation(user_id=ann.id, title="Ann", start_date=date(2026, 7, 1), end_date=date(2026, 7, 4),
                           people=[ann]))
        db.commit()
    # What a later migration that changes the users table does: copy, drop, rename.
    with engine.connect() as c, foreign_keys_off(c):
        with Operations(MigrationContext.configure(c)).batch_alter_table("users", recreate="always"):
            pass
        c.commit()
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM reservations")).scalar() == 1
        assert c.execute(text("SELECT count(*) FROM reservation_people")).scalar() == 1
        assert c.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
