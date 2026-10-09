import asyncio
import json
import secrets
from datetime import datetime, timezone
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from . import cache, live, portraits, schemas, tracks
from .config import settings
from .ingest import short_race_name, short_team_name, status
from .models import ConstructorStanding, Driver, DriverStanding, Race, Result, Session, SessionLocal, Team
from .racemode import COUNTDOWN_WINDOW, LABEL, RESULTS_WINDOW, race_mode, session_state


def require_key(x_api_key: str | None = Header(None)):
    if settings.api_key and not (x_api_key and secrets.compare_digest(x_api_key.encode(), settings.api_key.encode())):
        raise HTTPException(401, "Invalid or missing API key")


router = APIRouter(prefix="/api", dependencies=[Depends(require_key)])

ROUND = Path(ge=1, le=30)
# Annotated, not shared Path()/Query() defaults: FastAPI binds a shared instance to the first
# parameter name it sees, which broke /api/teams/{team_id} (it looked for driver_id).
Slug = Annotated[str, Path(pattern=r"^[a-z0-9_]{1,40}$")]


def now() -> datetime:
    return datetime.now(timezone.utc)


def _dump(model) -> dict | list:
    if isinstance(model, list):
        return [m.model_dump(mode="json") for m in model]
    return model.model_dump(mode="json") if model is not None else None


# ---------- query helpers (plain functions so the snapshot can reuse them) ----------

def current_season(db) -> int:
    season = db.scalar(select(func.max(Race.season)))
    if season is None:
        raise HTTPException(503, "Schedule not loaded yet")
    return season


def session_out(s: Session, t: datetime) -> schemas.Session:
    return schemas.Session(id=s.id, round=s.round, type=s.type, label=LABEL[s.type], starts_at=s.starts_at,
                           ends_at=s.ends_at, state=session_state(s.starts_at, s.ends_at, t))


def race_out(db, race: Race, t: datetime) -> schemas.Race:
    sessions = db.scalars(select(Session).where(Session.season == race.season, Session.round == race.round)
                          .order_by(Session.starts_at)).all()
    return schemas.Race(season=race.season, round=race.round, name=race.name, short_name=short_race_name(race.name),
                        circuit_name=race.circuit_name, locality=race.locality, country=race.country,
                        country_code=race.country_code, laps_total=race.laps_total,
                        sessions=[session_out(s, t) for s in sessions])


def next_race(db, t: datetime) -> Race | None:
    """The weekend in progress (including the results window after its last session), else the next one."""
    s = db.scalars(select(Session).where(Session.ends_at > t - RESULTS_WINDOW).order_by(Session.starts_at)).first()
    if s is None:
        return None
    return db.get(Race, (s.season, s.round))


def driver_out(d: Driver, team: Team | None) -> schemas.Driver:
    return schemas.Driver(id=d.id, code=d.code, number=d.number, first_name=d.first_name, last_name=d.last_name,
                          nationality=d.nationality, country_code=d.country_code, team_id=d.team_id,
                          team_name=team.name if team else None, team_color=team.color if team else None,
                          race_number=portraits.openf1_driver(d.code).get("number") or d.number)


def driver_standings(db, season: int) -> list[schemas.DriverStanding]:
    rows = db.execute(select(DriverStanding, Driver, Team).join(Driver, Driver.id == DriverStanding.driver_id)
                      .outerjoin(Team, Team.id == Driver.team_id).where(DriverStanding.season == season)
                      .order_by(DriverStanding.position)).all()
    return [schemas.DriverStanding(position=s.position, driver_id=d.id, code=d.code,
                                   name=f"{d.first_name} {d.last_name}", team_id=d.team_id,
                                   team_name=t.name if t else None, team_color=t.color if t else None,
                                   points=s.points, wins=s.wins) for s, d, t in rows]


def constructor_standings(db, season: int) -> list[schemas.ConstructorStanding]:
    rows = db.execute(select(ConstructorStanding, Team).join(Team, Team.id == ConstructorStanding.team_id)
                      .where(ConstructorStanding.season == season).order_by(ConstructorStanding.position)).all()
    return [schemas.ConstructorStanding(position=s.position, team_id=t.id, name=t.name,
                                        short_name=short_team_name(t.name), color=t.color, points=s.points,
                                        wins=s.wins) for s, t in rows]


def driver_detail(db, driver_id: str, season: int, t: datetime) -> schemas.DriverDetail | None:
    d = db.get(Driver, driver_id)
    if d is None:
        return None
    team = db.get(Team, d.team_id) if d.team_id else None
    standing = db.get(DriverStanding, (season, driver_id))
    mine = select(Result).where(Result.season == season, Result.driver_id == driver_id)
    races = db.scalars(mine.where(Result.session_type == "RACE").order_by(Result.round.desc())).all()
    poles = db.scalar(select(func.count()).select_from(
        mine.where(Result.session_type == "QUALIFYING", Result.position == 1).subquery()))
    weekend = []
    race = next_race(db, t)
    if race and race.season == season:
        order = {"SPRINT_QUALIFYING": 0, "SPRINT": 1, "QUALIFYING": 2, "RACE": 3}
        rows = db.scalars(mine.where(Result.round == race.round)).all()
        weekend = [schemas.WeekendResult(session_type=r.session_type, position=r.position, gap=r.gap)
                   for r in sorted(rows, key=lambda r: order.get(r.session_type, 9))]
    return schemas.DriverDetail(**driver_out(d, team).model_dump(), season=season,
                                position=standing.position if standing else None,
                                points=standing.points if standing else 0, wins=standing.wins if standing else 0,
                                podiums=sum(1 for r in races if r.position and r.position <= 3),
                                poles=poles or 0, last5=[r.position for r in races[:5]], weekend=weekend)


def timing_for(session_id: str) -> dict | None:
    return cache.get_json(f"timing:{session_id}")


def results_timing(db, s: Session) -> dict | None:
    """Final classification: Jolpica's official results (race/sprint/quali, penalties included), else the live
    processor's last snapshot (practice, or before Jolpica publishes)."""
    rows = db.execute(select(Result, Driver, Team).join(Driver, Driver.id == Result.driver_id)
                      .outerjoin(Team, Team.id == Result.team_id)
                      .where(Result.season == s.season, Result.round == s.round, Result.session_type == s.type,
                             Result.position.is_not(None)).order_by(Result.position)).all()
    if not rows:
        cached = timing_for(s.id)
        return {**cached, "final": s.ends_at <= now()} if cached else None
    race = db.get(Race, (s.season, s.round))
    return {"session_id": s.id, "session_type": s.type, "phase": None, "lap": None,
            "laps_total": race.laps_total if race else None, "final": True, "updated_at": s.ends_at.isoformat(),
            "rows": [{"position": r.position, "driver_number": d.number or 0, "code": d.code,
                      "team_color": tm.color if tm else None,
                      "time": r.gap if s.type == "QUALIFYING" else None,
                      "gap": None if s.type == "QUALIFYING" or r.position == 1 else r.gap, "interval": None,
                      "sectors": None, "in_pit": False, "drs": None} for r, d, tm in rows]}


# ---------- routes ----------

@router.get("/season/current", response_model=schemas.Season)
def season_current():
    def compute():
        with SessionLocal() as db:
            season = current_season(db)
            rounds = db.scalar(select(func.count()).select_from(Race).where(Race.season == season))
            race = next_race(db, now())
            return _dump(schemas.Season(year=season, rounds=rounds, next_round=race.round if race else None))
    return cache.cached("api:season", 300, compute)


@router.get("/races", response_model=list[schemas.Race])
def races():
    def compute():
        with SessionLocal() as db:
            season = current_season(db)
            t = now()
            return _dump([race_out(db, r, t) for r in
                          db.scalars(select(Race).where(Race.season == season).order_by(Race.round))])
    return cache.cached("api:races", 300, compute)


@router.get("/races/next", response_model=schemas.Race)
def races_next():
    def compute():
        with SessionLocal() as db:
            race = next_race(db, now())
            return _dump(race_out(db, race, now())) if race else None
    data = cache.cached("api:races:next", 60, compute)
    if data is None:
        raise HTTPException(404, "Season finished")
    return data


@router.get("/races/{round}", response_model=schemas.Race)
def race_by_round(round: int = ROUND):
    with SessionLocal() as db:
        race = db.get(Race, (current_season(db), round))
        if race is None:
            raise HTTPException(404, "No such round")
        return race_out(db, race, now())


@router.get("/races/{round}/track", responses={404: {"description": "No earlier race here with position data"}})
def race_track(round: int = ROUND):
    """3D outline of the round's circuit, from a real lap of an earlier race there: points are [x, y, metres up],
    x/y scaled into [-1, 1]. Built once per circuit, then served from disk."""
    with SessionLocal() as db:
        race = db.get(Race, (current_season(db), round))
    try:
        data = tracks.layout(race) if race else None
    except httpx.HTTPError:  # OpenF1 busy or down: nothing is cached, so the next request tries again
        raise HTTPException(503, "Track data is temporarily unavailable")
    if data is None:
        raise HTTPException(404, "No track layout for this round")
    return Response(json.dumps(data), media_type="application/json", headers={"Cache-Control": "public, max-age=86400"})


@router.get("/session/next", response_model=schemas.Session)
def session_next():
    with SessionLocal() as db:
        s = db.scalars(select(Session).where(Session.ends_at > now()).order_by(Session.starts_at)).first()
        if s is None:
            raise HTTPException(404, "Season finished")
        return session_out(s, now())


@router.get("/session/live", response_model=schemas.Timing, responses={204: {"description": "No live session"}})
def session_live():
    data = cache.get_json(live.LIVE_KEY)
    return data if data else Response(status_code=204)


@router.get("/session/live/stream")
async def session_live_stream(request: Request):
    """SSE: `event: timing` with a Timing payload on every change; comment heartbeat every 15 s."""
    q: asyncio.Queue = asyncio.Queue(maxsize=1)

    async def events():
        live.subscribers.add(q)  # inside the generator, so the finally below always runs if this did
        try:
            if current := cache.get_json(live.LIVE_KEY):
                yield f"event: timing\ndata: {json.dumps(current)}\n\n"
            while not await request.is_disconnected():
                try:
                    snap = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"event: timing\ndata: {json.dumps(snap)}\n\n"
                except TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            live.subscribers.discard(q)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/session/{session_id}/timing", response_model=schemas.Timing)
def session_timing(session_id: str = Path(pattern=r"^\d{4}-\d{1,2}-[a-z_]+$")):
    with SessionLocal() as db:
        s = db.get(Session, session_id)
        if s is None:
            raise HTTPException(404, "No such session")
        data = results_timing(db, s)
    if data is None:
        raise HTTPException(404, "No timing for this session")
    return data


@router.get("/standings/drivers", response_model=list[schemas.DriverStanding])
def standings_drivers():
    def compute():
        with SessionLocal() as db:
            return _dump(driver_standings(db, current_season(db)))
    return cache.cached("api:standings:drivers", 300, compute)


@router.get("/standings/constructors", response_model=list[schemas.ConstructorStanding])
def standings_constructors():
    def compute():
        with SessionLocal() as db:
            return _dump(constructor_standings(db, current_season(db)))
    return cache.cached("api:standings:constructors", 300, compute)


@router.get("/drivers", response_model=list[schemas.Driver])
def drivers():
    def compute():
        with SessionLocal() as db:
            season = current_season(db)
            active = select(Result.driver_id).where(Result.season == season)
            rows = db.execute(select(Driver, Team).outerjoin(Team, Team.id == Driver.team_id)
                              .where(Driver.id.in_(active)).order_by(Driver.last_name)).all()
            return _dump([driver_out(d, t) for d, t in rows])
    return cache.cached("api:drivers", 300, compute)


Season = Annotated[int | None, Query(ge=1950, le=2100, description="Defaults to the current season")]


@router.get("/drivers/{driver_id}", response_model=schemas.DriverDetail)
def driver(driver_id: Slug, season: Season = None):
    with SessionLocal() as db:
        detail = driver_detail(db, driver_id, season or current_season(db), now())
    if detail is None:
        raise HTTPException(404, "No such driver")
    return detail


@router.get("/drivers/{driver_id}/silhouette.png", response_class=Response,
            responses={200: {"content": {"image/png": {}}, "description": "Driver portrait with their glowing helmet"}, 404: {}})
def driver_silhouette(driver_id: Slug, size: Annotated[int, Query(ge=1, le=1336)] = 432):
    """The driver's official headshot in full colour, with their helmet glowing in the team colour in front of it
    (the face alone when F1 has no helmet render). PNG with a transparent background. The path still says
    silhouette, the old style, so installed apps keep working."""
    with SessionLocal() as db:
        d = db.get(Driver, driver_id)
        team = db.get(Team, d.team_id) if d and d.team_id else None
    # Served at the smallest official rendition that covers the requested size.
    size = min((r for r in portraits.RENDITIONS if r >= size), default=max(portraits.RENDITIONS))
    png = portraits.portrait(d.code, d.last_name, team.color or "FFFFFF", size) if d and team else None
    if png is None:
        raise HTTPException(404, "No portrait for this driver")
    return Response(png, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


@router.get("/teams", response_model=list[schemas.Team])
def teams():
    def compute():
        with SessionLocal() as db:
            season = current_season(db)
            active = select(ConstructorStanding.team_id).where(ConstructorStanding.season == season)
            return _dump([_team_out(db, t) for t in db.scalars(select(Team).where(Team.id.in_(active))
                                                                .order_by(Team.name))])
    return cache.cached("api:teams", 300, compute)


@router.get("/teams/{team_id}", response_model=schemas.Team)
def team(team_id: Slug):
    with SessionLocal() as db:
        t = db.get(Team, team_id)
        if t is None:
            raise HTTPException(404, "No such team")
        return _team_out(db, t)


def _team_out(db, t: Team) -> schemas.Team:
    # Drivers who raced for the team this season: past-season and replaced drivers keep a stale team_id.
    raced = select(Result.driver_id).where(Result.season == current_season(db), Result.team_id == t.id)
    drivers = db.scalars(select(Driver.id).where(Driver.team_id == t.id, Driver.id.in_(raced))).all()
    return schemas.Team(id=t.id, name=t.name, short_name=short_team_name(t.name), color=t.color,
                        nationality=t.nationality, drivers=list(drivers))


@router.get("/status", response_model=schemas.Status)
def api_status():
    from .models import engine

    return schemas.Status(ok=status["jolpica"]["ok"], database=engine.dialect.name, cache=cache.backend.name,
                          live=cache.get_json(live.LIVE_KEY) is not None, live_unavailable=live.live_unavailable,
                          sources={k: schemas.SourceStatus(**v) for k, v in status.items()}, now=now())


@router.get("/widgets/snapshot", response_model=schemas.WidgetSnapshot)
def widget_snapshot(driver: str | None = Query(None, pattern=r"^[a-z0-9_]{1,40}$"), season: Season = None):
    """Everything any widget needs, in one request. 30 s cache per driver."""
    if driver:  # unknown slugs share one entry, so made-up keys can't grow the cache
        with SessionLocal() as db:
            if db.get(Driver, driver) is None:
                driver = None
    season = season if driver else None
    return cache.cached(f"api:snapshot:{driver}:{season}", 30, lambda: _dump(build_snapshot(driver, season=season)))


def build_snapshot(driver_id: str | None, t: datetime | None = None, season: int | None = None) -> schemas.WidgetSnapshot:
    t = t or now()
    driver_season = season
    with SessionLocal() as db:
        season = current_season(db)
        race = next_race(db, t)
        sessions = db.scalars(select(Session).where(Session.season == season)).all()
        mode, focus = race_mode(sessions, t)
        upcoming = min((s for s in sessions if s.ends_at > t), key=lambda s: s.starts_at, default=None)
        live_timing = cache.get_json(live.LIVE_KEY) if mode == "live" else None
        results = results_timing(db, focus) if mode == "results" and focus else None
        if mode == "results" and results is None:  # nothing classified to show (e.g. practice without OpenF1)
            mode = "countdown" if upcoming and upcoming.starts_at - t <= COUNTDOWN_WINDOW else "next"
        return schemas.WidgetSnapshot(
            generated_at=t, mode=mode, race=race_out(db, race, t) if race else None,
            next_session=session_out(upcoming, t) if upcoming else None, live=live_timing, results=results,
            drivers=driver_standings(db, season)[:10], constructors=constructor_standings(db, season)[:10],
            driver=driver_detail(db, driver_id, driver_season or season, t) if driver_id else None,
            live_unavailable=live.live_unavailable)
