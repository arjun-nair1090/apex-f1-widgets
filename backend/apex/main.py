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
    for season in filter(None, settings.extra_seasons.split(",")):
        await asyncio.to_thread(ingest.sync, season.strip())
    while True:
        await asyncio.to_thread(ingest.sync)
        await asyncio.sleep(await asyncio.to_thread(_sync_interval))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    tasks = [asyncio.create_task(live.run_forever())]
    if settings.ingest_on_startup:
        tasks.append(asyncio.create_task(ingest_forever()))
    yield
    for t in tasks:
        t.cancel()


app = FastAPI(title="APEX API", version="1.0.0", lifespan=lifespan,
              description="The F1 data layer that lives everywhere.")

# ponytail: per-process token bucket keyed by client IP; move to Redis INCR if you run several replicas.
_buckets: dict[str, tuple[float, float]] = {}


@app.middleware("http")
async def guard(request: Request, call_next):
    if request.url.path.startswith("/api") and not request.url.path.endswith("/stream"):
        ip = request.client.host if request.client else "?"
        rate = settings.rate_limit_per_minute / 60
        tokens, last = _buckets.get(ip, (settings.rate_limit_per_minute, time.monotonic()))
        now = time.monotonic()
        tokens = min(settings.rate_limit_per_minute, tokens + (now - last) * rate)
        if tokens < 1:
            return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429,
                                headers={"Retry-After": str(int((1 - tokens) / rate) + 1)})
        _buckets[ip] = (tokens - 1, now)
    try:
        response = await call_next(request)
    except Exception:
        log.exception("unhandled error on %s", request.url.path)  # details stay in logs, never in responses
        response = JSONResponse({"detail": "Internal error"}, status_code=500)
    response.headers["X-Content-Type-Options"] = "nosniff"
    if settings.force_https:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


app.include_router(router)
app.mount("/", StaticFiles(directory=Path(__file__).parent / "preview", html=True), name="preview")
