import json
import time

from .config import settings


class _Memory:
    # ponytail: per-process dict; set REDIS_URL when running more than one worker.
    name = "memory"
    MAX_KEYS = 2000

    def __init__(self):
        self._d: dict[str, tuple[float, str]] = {}

    def get(self, key):
        hit = self._d.get(key)
        if hit and hit[0] > time.monotonic():
            return hit[1]
        self._d.pop(key, None)
        return None

    def set(self, key, value, ttl):
        if len(self._d) >= self.MAX_KEYS:  # bounded: drop the quarter closest to expiry
            for k, _ in sorted(list(self._d.items()), key=lambda kv: kv[1][0])[: len(self._d) // 4 or 1]:
                self._d.pop(k, None)
        self._d[key] = (time.monotonic() + ttl, value)

    def delete_prefix(self, prefix):
        # Request threads write while ingest deletes: iterate over a snapshot of the keys.
        for k in [k for k in list(self._d) if k.startswith(prefix)]:
            self._d.pop(k, None)


class _Redis:
    name = "redis"

    def __init__(self, url):
        import redis

        self._r = redis.Redis.from_url(url, decode_responses=True)

    def get(self, key):
        return self._r.get(key)

    def set(self, key, value, ttl):
        self._r.set(key, value, ex=int(ttl))

    def delete_prefix(self, prefix):
        for k in self._r.scan_iter(f"{prefix}*"):
            self._r.delete(k)


backend = _Redis(settings.redis_url) if settings.redis_url else _Memory()


def get_json(key):
    raw = backend.get(key)
    return json.loads(raw) if raw else None


def set_json(key, value, ttl):
    backend.set(key, json.dumps(value, default=str), ttl)


def cached(key, ttl, compute):
    hit = get_json(key)
    if hit is not None:
        return hit
    value = compute()
    set_json(key, value, ttl)
    return value
