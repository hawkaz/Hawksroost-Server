from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from . import config


class Base(DeclarativeBase):
    pass


def make_engine(url: str | None = None):
    engine = create_engine(
        url or f"sqlite:///{config.DB_PATH}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=30000")
        cur.close()

    return engine


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def foreign_keys_off(connection):
    """For schema changes. SQLite changes a table by rebuilding it (copy, drop, rename),
    and with foreign keys on, dropping the old copy also deletes every row that points
    at it (ON DELETE CASCADE): rebuilding users would take every booking with it."""
    connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
    connection.commit()
    try:
        yield connection
    finally:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.commit()


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
