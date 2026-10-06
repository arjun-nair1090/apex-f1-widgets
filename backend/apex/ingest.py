"""Jolpica (Ergast-compatible) → normalize → database. Schedule, standings, results."""

import logging
import re
import time
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import delete, select

from . import cache
from .config import settings
from .models import ConstructorStanding, Driver, DriverStanding, Race, Result, Session, SessionLocal, Team
from .racemode import DURATION_MIN

log = logging.getLogger("apex.ingest")

# Source health, read by /api/status.
status: dict[str, dict] = {"jolpica": {"ok": False, "last_success": None, "error": None},
                           "openf1": {"ok": False, "last_success": None, "error": None}}

JOLPICA_SESSIONS = {"FirstPractice": "FP1", "SecondPractice": "FP2", "ThirdPractice": "FP3",
                    "SprintQualifying": "SPRINT_QUALIFYING", "SprintShootout": "SPRINT_QUALIFYING",
                    "Sprint": "SPRINT", "Qualifying": "QUALIFYING"}

# Flags need ISO-3166 alpha-2; Jolpica gives names. Unknown → None (clients show no flag).
NATIONALITY_ISO = {
    "American": "US", "Argentine": "AR", "Argentinian": "AR", "Australian": "AU", "Austrian": "AT", "Belgian": "BE",
    "Brazilian": "BR", "British": "GB", "Canadian": "CA", "Chinese": "CN", "Danish": "DK", "Dutch": "NL",
    "Finnish": "FI", "French": "FR", "German": "DE", "Italian": "IT", "Japanese": "JP", "Mexican": "MX",
    "Monegasque": "MC", "New Zealander": "NZ", "Polish": "PL", "Spanish": "ES", "Swiss": "CH", "Thai": "TH",
    "Swedish": "SE", "Russian": "RU", "Indian": "IN", "Colombian": "CO", "Venezuelan": "VE", "Irish": "IE",
}
COUNTRY_ISO = {
    "Australia": "AU", "Austria": "AT", "Azerbaijan": "AZ", "Bahrain": "BH", "Belgium": "BE", "Brazil": "BR",
    "Canada": "CA", "China": "CN", "France": "FR", "Germany": "DE", "Hungary": "HU", "Italy": "IT", "Japan": "JP",
    "Malaysia": "MY", "Mexico": "MX", "Monaco": "MC", "Netherlands": "NL", "Portugal": "PT", "Qatar": "QA",
    "Russia": "RU", "Saudi Arabia": "SA", "Singapore": "SG", "Spain": "ES", "Turkey": "TR", "UAE": "AE",
    "United Arab Emirates": "AE", "UK": "GB", "United Kingdom": "GB", "USA": "US", "United States": "US",
    "Argentina": "AR", "South Africa": "ZA", "Korea": "KR", "India": "IN", "Vietnam": "VN", "Thailand": "TH",
}


def safe_hex(value) -> str | None:
    """Team colours come from OpenF1, an external source: only plain RRGGBB gets through. They end up in
    HTML style attributes (web preview) and in hex parsers (every native client)."""
    return value.upper() if isinstance(value, str) and re.fullmatch(r"[0-9A-Fa-f]{6}", value) else None


def short_race_name(name: str) -> str:
    return name.upper().replace("GRAND PRIX", "GP")


def short_team_name(name: str) -> str:
    n = name.upper().replace(" F1 TEAM", "").strip()
    return n if len(n) <= 9 else n.split()[0]


def _get(client: httpx.Client, path: str, **params) -> dict:
    for attempt in range(3):
        r = client.get(f"{settings.jolpica_base}/{path}", params=params)
        if r.status_code == 429:  # Jolpica: ~4 req/s burst, 500/h sustained
            time.sleep(2 ** attempt)
            continue
        r.raise_for_status()
        return r.json()["MRData"]
    r.raise_for_status()


def _all_races(client, path) -> list[dict]:
    """Paginate an endpoint whose payload is RaceTable.Races; results of one race may span pages."""
    races: dict[str, dict] = {}
    offset = 0
    while True:
        data = _get(client, path, limit=100, offset=offset)
        for race in data["RaceTable"]["Races"]:
            key = race["round"]
            list_key = next(k for k in ("Results", "QualifyingResults", "SprintResults") if k in race)
            races.setdefault(key, {**race, list_key: []})[list_key].extend(race[list_key])
        offset += 100
        if offset >= int(data["total"]):
            return list(races.values())


def _dt(d: dict) -> datetime:
    return datetime.fromisoformat(f"{d['date']}T{d.get('time', '00:00:00Z').replace('Z', '+00:00')}")


def _upsert_driver(db, d: dict, team_id: str | None):
    db.merge(Driver(id=d["driverId"], code=d.get("code") or d["familyName"][:3].upper(),
                    number=int(d["permanentNumber"]) if d.get("permanentNumber") else None,
                    first_name=d["givenName"], last_name=d["familyName"], nationality=d.get("nationality"),
                    country_code=NATIONALITY_ISO.get(d.get("nationality")), team_id=team_id))


def _upsert_team(db, c: dict):
    existing = db.get(Team, c["constructorId"])
    db.merge(Team(id=c["constructorId"], name=c["name"], nationality=c.get("nationality"),
                  color=existing.color if existing else None))


def sync(season: str = "current") -> None:
    with httpx.Client(timeout=20, headers={"User-Agent": "apex-widgets/1.0"}) as client, SessionLocal() as db:
        try:
            _sync(client, db, season)
            db.commit()
            status["jolpica"] = {"ok": True, "last_success": datetime.now(timezone.utc), "error": None}
        except Exception as e:  # keep serving the last good data
            db.rollback()
            log.exception("jolpica sync failed")
            status["jolpica"] = {**status["jolpica"], "ok": False, "error": type(e).__name__}
            return
        try:
            _sync_team_colors(client, db)
            db.commit()
        except Exception:
            db.rollback()
            log.warning("team colour sync failed", exc_info=True)
    cache.backend.delete_prefix("api:")


def _sync(client, db, season):
    schedule = _get(client, f"{season}.json", limit=100)["RaceTable"]
    year = int(schedule["season"])

    # Teams and drivers first: everything else references them.
    standings = _get(client, f"{year}/driverstandings.json", limit=100)["StandingsTable"]["StandingsLists"]
    cstandings = _get(client, f"{year}/constructorstandings.json", limit=100)["StandingsTable"]["StandingsLists"]
    results = _all_races(client, f"{year}/results.json")
    qualifying = _all_races(client, f"{year}/qualifying.json")
    sprints = _all_races(client, f"{year}/sprint.json")

    for lst in cstandings:
        for s in lst["ConstructorStandings"]:
            _upsert_team(db, s["Constructor"])
    for race in results + qualifying + sprints:
        for r in race.get("Results") or race.get("QualifyingResults") or race.get("SprintResults"):
            _upsert_team(db, r["Constructor"])
    db.flush()
    # Latest race wins for a driver's team (mid-season swaps), then standings fill the rest.
    for race in sorted(results + qualifying, key=lambda r: int(r["round"])):
        for r in race.get("Results") or race.get("QualifyingResults"):
            _upsert_driver(db, r["Driver"], r["Constructor"]["constructorId"])
    for lst in standings:
        for s in lst["DriverStandings"]:
            if not db.get(Driver, s["Driver"]["driverId"]):
                _upsert_team(db, s["Constructors"][-1])
                _upsert_driver(db, s["Driver"], s["Constructors"][-1]["constructorId"])
    db.flush()

    winner_laps = {int(r["round"]): int(r["Results"][0]["laps"]) for r in results if r["Results"]}
    next_round = None
    now = datetime.now(timezone.utc)
    for r in schedule["Races"]:
        rnd = int(r["round"])
        loc = r["Circuit"]["Location"]
        race_start = _dt(r)
        if next_round is None and race_start + timedelta(minutes=DURATION_MIN["RACE"]) > now:
            next_round = rnd
        prev = db.get(Race, (year, rnd))
        laps = winner_laps.get(rnd) or (prev.laps_total if prev else None)
        if laps is None and rnd == next_round:
            laps = _previous_edition_laps(client, year, r["Circuit"]["circuitId"])
        db.merge(Race(season=year, round=rnd, name=r["raceName"], circuit_id=r["Circuit"]["circuitId"],
                      circuit_name=r["Circuit"]["circuitName"], locality=loc.get("locality"),
                      country=loc.get("country"), country_code=COUNTRY_ISO.get(loc.get("country")), laps_total=laps))
        db.flush()
        sessions = [(t, _dt(r[k])) for k, t in JOLPICA_SESSIONS.items() if k in r] + [("RACE", race_start)]
        for typ, start in sessions:
            sid = f"{year}-{rnd}-{typ.lower()}"
            old = db.get(Session, sid)
            # Keep an OpenF1-observed end time if live.py recorded one.
            end = old.ends_at if old and old.starts_at == start else start + timedelta(minutes=DURATION_MIN[typ])
            db.merge(Session(id=sid, season=year, round=rnd, type=typ, starts_at=start, ends_at=end))

    db.execute(delete(DriverStanding).where(DriverStanding.season == year))
    for lst in standings:
        for s in lst["DriverStandings"]:
            db.add(DriverStanding(season=year, driver_id=s["Driver"]["driverId"], position=int(s["position"]),
                                  points=float(s["points"]), wins=int(s["wins"])))
    db.execute(delete(ConstructorStanding).where(ConstructorStanding.season == year))
    for lst in cstandings:
        for s in lst["ConstructorStandings"]:
            db.add(ConstructorStanding(season=year, team_id=s["Constructor"]["constructorId"],
                                       position=int(s["position"]), points=float(s["points"]), wins=int(s["wins"])))

    for races, typ, key in ((results, "RACE", "Results"), (sprints, "SPRINT", "SprintResults"),
                            (qualifying, "QUALIFYING", "QualifyingResults")):
        for race in races:
            for r in race[key]:
                if typ == "QUALIFYING":
                    gap = r.get("Q3") or r.get("Q2") or r.get("Q1")
                else:
                    gap = (r.get("Time") or {}).get("time") or (r["status"] if r.get("status") != "Finished" else None)
                classified = typ == "QUALIFYING" or r.get("positionText", "").isdigit()
                db.merge(Result(season=year, round=int(race["round"]), session_type=typ,
                                driver_id=r["Driver"]["driverId"], team_id=r["Constructor"]["constructorId"],
                                position=int(r["position"]) if classified else None,
                                grid=int(r["grid"]) if r.get("grid") else None,
                                points=float(r["points"]) if r.get("points") else None,
                                gap=gap, status=r.get("status")))


def _previous_edition_laps(client, year, circuit_id) -> int | None:
    try:
        races = _get(client, f"{year - 1}/circuits/{circuit_id}/results/1.json")["RaceTable"]["Races"]
        return int(races[0]["Results"][0]["laps"]) if races else None
    except Exception:
        return None


def _sync_team_colors(client, db):
    """Jolpica has no colours; OpenF1 does. Join on the three-letter driver code."""
    headers = {"Authorization": f"Bearer {settings.openf1_token}"} if settings.openf1_token else {}
    r = client.get(f"{settings.openf1_base}/drivers", params={"session_key": "latest"}, headers=headers)
    r.raise_for_status()
    colour_by_code = {d["name_acronym"]: c for d in r.json() if (c := safe_hex(d.get("team_colour")))}
    for driver in db.scalars(select(Driver)):
        team = db.get(Team, driver.team_id) if driver.team_id else None
        if team and driver.code in colour_by_code:
            team.color = colour_by_code[driver.code]
