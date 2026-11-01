import os
import tempfile

os.environ["HAWK_DATA_DIR"] = tempfile.mkdtemp(prefix="hawk-test-")
os.environ["HAWK_GO2RTC_URL"] = "http://127.0.0.1:9"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import config  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.users import create_user  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    config.ensure_dirs()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    for limiter in _limiters():
        limiter.hits.clear()
    from app import cache
    cache.clear()
    yield


def _limiters():
    from app.routers import auth
    from app.security import RateLimiter
    return [v for mod in (auth,) for v in vars(mod).values() if isinstance(v, RateLimiter)]


@pytest.fixture
def client():
    with TestClient(app, base_url="https://testserver") as c:
        yield c


def make_user(role="member", email=None, password="correct horse"):
    with SessionLocal() as db:
        u = create_user(db, role.title(), email or f"{role}@example.com", role,
                        password_hash=hash_password(password))
        return u.id


def login(client, role="member"):
    email = f"{role}@example.com"
    make_user(role, email)
    r = client.post("/api/auth/login", json={"email": email, "password": "correct horse"})
    assert r.status_code == 200, r.text
    return client
