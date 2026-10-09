import asyncio
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from . import ingest, live
from .api import router
from .config import settings
from .models import Session, SessionLocal, init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("apex")


def _sync_interval() -> float:
    """Results change for ~2 h after a session ends; poll faster then, idle otherwise."""
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        recent = db.scalar(select(Session.id).where(Session.ends_at <= now, Session.ends_at > now - timedelta(hours=2)))
    return 300 if recent else settings.sync_minutes * 60


async def ingest_forever():
    # Past seasons once, first: the current-season pass then leaves every driver on their current team.
    for season in [s.strip() for s in settings.extra_seasons.split(",") if s.strip()]:
        await asyncio.to_thread(ingest.sync, season)
    while True:
        await asyncio.to_thread(ingest.sync)
        await asyncio.sleep(await asyncio.to_thread(_sync_interval))


async def supervised(name, loop):
    """A background loop must outlive any one failure (DB blip, Redis down, bad payload): log and restart."""
    while True:
        try:
            await loop()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("%s loop crashed; restarting in 30 s", name)
            await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    tasks = []
    if settings.background_jobs:
        tasks.append(asyncio.create_task(supervised("live", live.run_forever)))
        if settings.ingest_on_startup:
            tasks.append(asyncio.create_task(supervised("ingest", ingest_forever)))
    yield
    for t in tasks:
        t.cancel()


app = FastAPI(title="APEX API", version="1.0.0", lifespan=lifespan,
              description="The F1 data layer that lives everywhere.")

# ponytail: per-process token bucket keyed by client IP; move to Redis INCR if you run several replicas.
# Behind a proxy, run uvicorn with --forwarded-allow-ips=<proxy> so client.host is the real client.
_buckets: dict[str, tuple[float, float]] = {}
MAX_BUCKETS = 10_000


@app.middleware("http")
async def guard(request: Request, call_next):
    # Every /api request costs a token, SSE included (one per connection). No path exemptions: any
    # suffix match also matches /api/drivers/{id} with id="stream".
    response = None
    if request.url.path.startswith("/api"):
        ip = request.client.host if request.client else "?"
        rate = settings.rate_limit_per_minute / 60
        now = time.monotonic()
        if len(_buckets) > MAX_BUCKETS:  # a bucket idle for a minute is full again: forget it
            for k in [k for k, (_, last) in list(_buckets.items()) if now - last > 60]:
                _buckets.pop(k, None)
        tokens, last = _buckets.get(ip, (settings.rate_limit_per_minute, now))
        tokens = min(settings.rate_limit_per_minute, tokens + (now - last) * rate)
        if tokens < 1:
            response = JSONResponse({"detail": "Rate limit exceeded"}, status_code=429,
                                    headers={"Retry-After": str(int((1 - tokens) / rate) + 1)})
        else:
            _buckets[ip] = (tokens - 1, now)
    if response is None:
        try:
            response = await call_next(request)
        except Exception:
            log.exception("unhandled error on %s", request.url.path)  # details stay in logs, never in responses
            response = JSONResponse({"detail": "Internal error"}, status_code=500)
    response.headers["X-Content-Type-Options"] = "nosniff"
    if settings.force_https:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


class Revalidated(StaticFiles):
    """Pages, scripts and fonts are rechecked on every load (a cheap 304 when unchanged). Left to guess, WebView2 kept
    an old widgets.js for hours, and with it the old portrait URLs, so a new portrait style never showed."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


app.include_router(router)
app.mount("/", Revalidated(directory=Path(__file__).parent / "preview", html=True), name="preview")
