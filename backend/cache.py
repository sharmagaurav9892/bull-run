"""Tiny thread-safe TTL cache. Keeps the upstream APIs happy on repeat lookups."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, Tuple


class TTLCache:
    def __init__(self, ttl_seconds: int = 600, max_entries: int = 512):
        self.ttl = ttl_seconds
        self.max_entries = max_entries
        self._lock = threading.Lock()
        self._store: Dict[Any, Tuple[float, Any]] = {}

    def get(self, key: Any):
        with self._lock:
            hit = self._store.get(key)
            if not hit:
                return None
            expires_at, value = hit
            if expires_at < time.time():
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: Any, value: Any) -> None:
        with self._lock:
            if len(self._store) >= self.max_entries:
                # cheap eviction: drop the oldest
                oldest = min(self._store.items(), key=lambda kv: kv[1][0])[0]
                self._store.pop(oldest, None)
            self._store[key] = (time.time() + self.ttl, value)

    def get_or_set(self, key: Any, factory: Callable[[], Any]):
        cached = self.get(key)
        if cached is not None:
            return cached
        value = factory()
        if value is not None:
            self.set(key, value)
        return value
