"""OpenF1 live processor: incremental polling → one Timing snapshot → cache + SSE subscribers."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select

from . import cache
from .config import settings
from .ingest import status
from .models import Race, Session, SessionLocal
from .racemode import race_mode

log = logging.getLogger("apex.live")

LIVE_KEY = "timing:live"
FINAL_TTL = 12 * 3600  # results mode reads the final classification for up to 90 min; keep it for the day
subscribers: set[asyncio.Queue] = set()
live_unavailable = False


def fmt_lap(seconds: float | None) -> str | None:
    if not seconds:
        return None
    m, s = divmod(seconds, 60)
    return f"{int(m)}:{s:06.3f}"


def fmt_gap(value) -> str | None:
    if value is None or value == 0:
        return None
    if isinstance(value, str):  # OpenF1 sends "+1 LAP" for lapped cars
        return value.upper()
    return f"+{value:.3f}"


class SessionState:
    """Everything seen so far for one OpenF1 session."""

    def __init__(self, session_key: int):
        self.key = session_key
        self.drivers: dict[int, dict] = {}
        self.position: dict[int, int] = {}
        self.interval: dict[int, dict] = {}
        self.laps: dict[int, dict[int, dict]] = {}  # driver → lap_number → lap
        self.pits: dict[int, dict] = {}  # driver → latest pit
        self.phase: str | None = None
        self.cursor: dict[str, str] = {}

    def apply(self, endpoint: str, rows: list[dict]) -> None:
        for r in rows:
            n = r.get("driver_number")
            if endpoint == "drivers":
                self.drivers[n] = r
            elif endpoint == "position":
                self.position[n] = r["position"]
            elif endpoint == "intervals":
                self.interval[n] = r
            elif endpoint == "laps":
                self.laps.setdefault(n, {})[r["lap_number"]] = r
            elif endpoint == "pit":
                self.pits[n] = r
            elif endpoint == "race_control" and r.get("qualifying_phase"):
                self.phase = f"Q{r['qualifying_phase']}"
        if rows and endpoint != "drivers":
            field = "date_start" if endpoint == "laps" else "date"
            stamps = [r[field] for r in rows if r.get(field)]
            if stamps:
                self.cursor[endpoint] = max(stamps)


def build_timing(st: SessionState, session_id: str, session_type: str, laps_total: int | None,
                 now: datetime, final: bool = False) -> dict:
    is_race = session_type in ("RACE", "SPRINT")
    done = {n: [l for l in laps.values() if l.get("lap_duration")] for n, laps in st.laps.items()}
    best = {n: min((l["lap_duration"] for l in ls), default=None) for n, ls in done.items()}

    # Sector bests across the session (overall) and per driver (personal).
    sector_keys = ("duration_sector_1", "duration_sector_2", "duration_sector_3")
    personal = {n: [min((l[k] for l in ls if l.get(k)), default=None) for k in sector_keys] for n, ls in done.items()}
    overall = [min((p[i] for p in personal.values() if p[i]), default=None) for i in range(3)]

    def sectors(n):
        if not done.get(n):
            return None
        last = max(done[n], key=lambda l: l["lap_number"])
        out = []
        for i, k in enumerate(sector_keys):
            v = last.get(k)
            out.append(None if not v else "purple" if v <= overall[i] else "green" if v <= personal[n][i] else "yellow")
        return out

    def in_pit(n):
        p = st.pits.get(n)
        if not p:
            return False
        entered = datetime.fromisoformat(p["date"])
        return now - entered < timedelta(seconds=p.get("lane_duration") or 35)

    order = sorted(st.position.items(), key=lambda kv: kv[1])
    leader_best = best.get(order[0][0]) if order else None
    rows = []
    for n, pos in order:
        d = st.drivers.get(n, {})
        if is_race:
            last = max(done.get(n) or [{}], key=lambda l: l.get("lap_number", 0))
            time_ = fmt_lap(last.get("lap_duration"))
            gap = fmt_gap(st.interval.get(n, {}).get("gap_to_leader"))
            interval = fmt_gap(st.interval.get(n, {}).get("interval"))
        else:
            time_ = fmt_lap(best.get(n))
            gap = fmt_gap(best[n] - leader_best) if best.get(n) and leader_best and pos > 1 else None
            interval = None
        rows.append({"position": pos, "driver_number": n, "code": d.get("name_acronym", str(n)),
                     "team_color": (d.get("team_colour") or "").upper() or None, "time": time_, "gap": gap,
                     "interval": interval, "sectors": sectors(n), "in_pit": in_pit(n),
                     "drs": None})  # 2026 regulations removed DRS; keep the field for sources that report it
    lap = max((max(l) for l in st.laps.values() if l), default=None) if is_race else None
    return {"session_id": session_id, "session_type": session_type, "phase": st.phase if session_type in
            ("QUALIFYING", "SPRINT_QUALIFYING") else None, "lap": lap, "laps_total": laps_total if is_race else None,
            "final": final, "updated_at": now.isoformat(), "rows": rows}


async def _fetch(client, endpoint, st: SessionState) -> list[dict]:
    url = f"{settings.openf1_base}/{endpoint}?session_key={st.key}"
    if endpoint in st.cursor:
        field = "date_start" if endpoint == "laps" else "date"
        url += f"&{field}>{st.cursor[endpoint].replace('+', '%2B')}"
    r = await client.get(url)
    if r.status_code == 404:  # OpenF1: no rows yet
        return []
    r.raise_for_status()
    return r.json()


def broadcast(snapshot: dict) -> None:
    for q in list(subscribers):
        if q.full():
            q.get_nowait()  # slow client: drop the stale snapshot, keep the newest
        q.put_nowait(snapshot)


def _current_live():
    """(session, race) if Race Mode says live right now, else None."""
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        window = db.scalars(select(Session).where(Session.starts_at <= now + timedelta(hours=1),
                                                  Session.ends_at >= now - timedelta(hours=1))).all()
        mode, s = race_mode(window, now)
        if mode != "live":
            return None
        return s, db.get(Race, (s.season, s.round))


async def run_forever() -> None:
    global live_unavailable
    headers = {"Authorization": f"Bearer {settings.openf1_token}"} if settings.openf1_token else {}
    st: SessionState | None = None
    current_id = None
    async with httpx.AsyncClient(timeout=10, headers=headers) as client:
        while True:
            live = await asyncio.to_thread(_current_live)
            if not live:
                if st and current_id:  # session just ended: publish the final classification once
                    cached = cache.get_json(f"timing:{current_id}")
                    if cached:
                        cached["final"] = True
                        cache.set_json(f"timing:{current_id}", cached, FINAL_TTL)
                        broadcast(cached)
                st, current_id, live_unavailable = None, None, False
                await asyncio.sleep(30)
                continue
            session, race = live
            try:
                if st is None or current_id != session.id:
                    meta = (await client.get(f"{settings.openf1_base}/sessions", params={"session_key": "latest"})).json()
                    if (not isinstance(meta, list) or not meta or abs(
                            datetime.fromisoformat(meta[0]["date_start"]) - session.starts_at) > timedelta(hours=1)):
                        raise RuntimeError("OpenF1 has not opened this session yet")
                    st, current_id = SessionState(meta[0]["session_key"]), session.id
                    await _record_end(session.id, meta[0].get("date_end"))
                endpoints = ["drivers"] if not st.drivers else []
                endpoints += ["position", "laps", "pit"]
                endpoints += ["intervals"] if session.type in ("RACE", "SPRINT") else ["race_control"]
                before = repr((st.position, st.interval, len(st.pits), sum(len(l) for l in st.laps.values()), st.phase))
                for ep in endpoints:
                    st.apply(ep, await _fetch(client, ep, st))
                now = datetime.now(timezone.utc)
                snapshot = build_timing(st, session.id, session.type, race.laps_total if race else None, now)
                cache.set_json(LIVE_KEY, snapshot, 60)
                cache.set_json(f"timing:{session.id}", snapshot, FINAL_TTL)
                if repr((st.position, st.interval, len(st.pits), sum(len(l) for l in st.laps.values()), st.phase)) != before:
                    broadcast(snapshot)
                live_unavailable = False
                status["openf1"] = {"ok": True, "last_success": now, "error": None}
            except Exception as e:  # 401 without a paid key during sessions, timeouts, etc.
                live_unavailable = True
                status["openf1"] = {**status["openf1"], "ok": False, "error": type(e).__name__}
                log.warning("live poll failed: %s", e)
                await asyncio.sleep(15)
            await asyncio.sleep(settings.live_poll_seconds)


async def _record_end(session_id: str, date_end: str | None) -> None:
    if not date_end:
        return

    def save():
        with SessionLocal() as db:
            s = db.get(Session, session_id)
            if s:
                s.ends_at = datetime.fromisoformat(date_end)
                db.commit()

    await asyncio.to_thread(save)
