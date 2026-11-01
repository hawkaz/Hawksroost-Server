"""A tiny in-process cache for answers that are slow to build and change slowly
(history charts). One uvicorn worker, so a dict is enough."""
import time
from collections.abc import Callable
from threading import Lock
from typing import Any

_store: dict[Any, tuple[float, Any]] = {}
_lock = Lock()


def cached(key: Any, ttl_s: float, build: Callable[[], Any]) -> Any:
    now = time.monotonic()
    with _lock:
        hit = _store.get(key)
        if hit and now - hit[0] < ttl_s:
            return hit[1]
    value = build()
    with _lock:
        _store[key] = (now, value)
    return value


def clear() -> None:
    with _lock:
        _store.clear()
