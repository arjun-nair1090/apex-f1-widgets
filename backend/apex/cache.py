import json
import time

from .config import settings


class _Memory:
    # ponytail: per-process dict; set REDIS_URL when running more than one worker.
    name = "memory"

    def __init__(self):
        self._d: dict[str, tuple[float, str]] = {}

    def get(self, key):
        hit = self._d.get(key)
        if hit and hit[0] > time.monotonic():
            return hit[1]
        self._d.pop(key, None)
        return None

    def set(self, key, value, ttl):
        self._d[key] = (time.monotonic() + ttl, value)

    def delete_prefix(self, prefix):
        for k in [k for k in self._d if k.startswith(prefix)]:
            del self._d[k]


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
