"""3D circuit outlines from a real lap: OpenF1 car positions (x, y, z) from a previous race at the venue."""

import json
import re
import time
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

import httpx

from .config import settings

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache" / "tracks"  # layouts don't change: fetch once
POINTS = 240


def _norm(s: str | None) -> str:
    return re.sub(r"[^a-z]", "", unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower())


def _openf1(client: httpx.Client, endpoint: str, query: str) -> list[dict]:
    for attempt in range(4):  # OpenF1's free tier allows ~3 requests/s: back off when told to
        r = client.get(f"{settings.openf1_base}/{endpoint}?{query}")
        if r.status_code != 429:
            break
        time.sleep(float(r.headers.get("Retry-After") or 2 ** attempt))
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return r.json()


def _find_race_session(client, race) -> dict | None:
    """The most recent earlier race at this venue, matched on the place or the circuit's name. Never on the country:
    a new circuit (2026 Madrid) must not borrow another track in the same country."""
    place, circuit = _norm(race.locality), _norm(race.circuit_name)
    near = lambda a, b: bool(a and b) and (a in b or b in a)
    for year in range(race.season - 1, race.season - 4, -1):
        for s in _openf1(client, "sessions", f"year={year}&session_name=Race"):
            if near(place, _norm(s.get("location"))) or near(circuit, _norm(s.get("circuit_short_name"))):
                return s
    return None


def _build(race) -> dict | None:
    headers = {"Authorization": f"Bearer {settings.openf1_token}"} if settings.openf1_token else {}
    with httpx.Client(timeout=30, headers=headers) as client:
        session = _find_race_session(client, race)
        if not session:
            return None
        key = session["session_key"]
        # One request for every lap (its lap_number filter misses some races); skip lap 1 and pit laps.
        laps = [l for l in _openf1(client, "laps", f"session_key={key}")
                if l.get("lap_duration") and l.get("date_start") and not l.get("is_pit_out_lap") and l.get("lap_number", 0) > 1]
        if not laps:
            return None
        lap = min(laps, key=lambda l: l["lap_duration"])  # fastest clean lap: no pit lane, full racing line
        start = datetime.fromisoformat(lap["date_start"])
        end = start + timedelta(seconds=lap["lap_duration"])
        enc = lambda t: t.isoformat().replace("+", "%2B")
        pts = _openf1(client, "location",
                      f"session_key={key}&driver_number={lap['driver_number']}&date>={enc(start)}&date<={enc(end)}")
    return normalize([(p["x"], p["y"], p["z"]) for p in pts if p.get("x") is not None], race.circuit_name,
                     session.get("year"))


def normalize(raw: list[tuple[int, int, int]], circuit: str, year: int | None) -> dict | None:
    """Centre and scale x/y into [-1, 1] (aspect kept), heights in metres above the lowest point (OpenF1 units: dm)."""
    # Drop parked samples (identical consecutive positions), then thin evenly to POINTS.
    pts = [p for i, p in enumerate(raw) if i == 0 or p[:2] != raw[i - 1][:2]]
    if len(pts) < 50:
        return None
    step = len(pts) / min(POINTS, len(pts))
    pts = [pts[int(i * step)] for i in range(min(POINTS, len(pts)))]
    xs, ys, zs = zip(*pts)
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    half = max(max(xs) - min(xs), max(ys) - min(ys)) / 2 or 1
    return {
        "circuit": circuit,
        "source_year": year,
        "span_m": round(half * 2 / 10),
        "elevation_m": round((max(zs) - min(zs)) / 10, 1),
        "points": [[round((x - cx) / half, 4), round((y - cy) / half, 4), round((z - min(zs)) / 10, 2)] for x, y, z in pts],
    }


def layout(race) -> dict | None:
    """Cached on disk per circuit; None when no earlier race at the venue has position data (e.g. a brand-new track)."""
    path = CACHE_DIR / f"{race.circuit_id}.json"
    if path.exists():
        return json.loads(path.read_text())
    data = _build(race)
    if data:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))
    return data
