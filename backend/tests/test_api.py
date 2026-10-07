"""Offline checks: Race Mode rules, timing builder, and the API over a seeded SQLite DB. Run: pytest -q"""

import os
import tempfile
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["INGEST_ON_STARTUP"] = "0"

from fastapi.testclient import TestClient  # noqa: E402

from apex import cache  # noqa: E402
from apex.api import build_snapshot  # noqa: E402
from apex.config import settings  # noqa: E402
from apex.ingest import safe_hex  # noqa: E402
from apex.live import SessionState, build_timing  # noqa: E402
from apex.main import app  # noqa: E402
from apex.models import (ConstructorStanding, Driver, DriverStanding, Race, Result, Session,  # noqa: E402
                         SessionLocal, Team, init_db)
from apex.racemode import race_mode, session_state  # noqa: E402

NOW = datetime.now(timezone.utc).replace(microsecond=0)


def seed():
    init_db()
    with SessionLocal() as db:
        db.add_all([Team(id="mercedes", name="Mercedes", color="00D7B6"),
                    Team(id="red_bull", name="Red Bull", color="4781D7")])
        db.flush()
        db.add_all([Driver(id="antonelli", code="ANT", number=12, first_name="Andrea Kimi", last_name="Antonelli",
                           nationality="Italian", country_code="IT", team_id="mercedes"),
                    Driver(id="max_verstappen", code="VER", number=1, first_name="Max", last_name="Verstappen",
                           nationality="Dutch", country_code="NL", team_id="red_bull")])
        db.add_all([Race(season=2026, round=16, name="Malaysian Grand Prix", circuit_id="sepang",
                         circuit_name="Sepang", locality=None, country="Malaysia", country_code="MY", laps_total=56),
                    Race(season=2026, round=17, name="Singapore Grand Prix", circuit_id="marina_bay",
                         circuit_name="Marina Bay", locality="Marina Bay", country="Singapore", country_code="SG",
                         laps_total=62)])
        db.flush()
        past = NOW - timedelta(days=2)
        q = NOW + timedelta(hours=2)  # quali in 2 h → countdown
        db.add_all([Session(id="2026-16-race", season=2026, round=16, type="RACE", starts_at=past,
                            ends_at=past + timedelta(hours=2)),
                    Session(id="2026-17-qualifying", season=2026, round=17, type="QUALIFYING", starts_at=q,
                            ends_at=q + timedelta(hours=1)),
                    Session(id="2026-17-race", season=2026, round=17, type="RACE", starts_at=q + timedelta(days=1),
                            ends_at=q + timedelta(days=1, hours=2))])
        db.add_all([DriverStanding(season=2026, driver_id="antonelli", position=1, points=320, wins=8),
                    DriverStanding(season=2026, driver_id="max_verstappen", position=2, points=298, wins=5),
                    ConstructorStanding(season=2026, team_id="mercedes", position=1, points=556, wins=11),
                    ConstructorStanding(season=2026, team_id="red_bull", position=2, points=461, wins=5)])
        for rnd, ant, ver in ((15, 1, 2), (16, 2, 1)):
            db.add_all([Result(season=2026, round=rnd, session_type="RACE", driver_id="antonelli", team_id="mercedes",
                               position=ant, gap=None if ant == 1 else "+2.307"),
                        Result(season=2026, round=rnd, session_type="RACE", driver_id="max_verstappen",
                               team_id="red_bull", position=ver, gap=None if ver == 1 else "+2.307"),
                        Result(season=2026, round=rnd, session_type="QUALIFYING", driver_id="antonelli",
                               team_id="mercedes", position=1, gap="1:38.100")])
        db.commit()


seed()
client = TestClient(app)


def test_race_mode_rules():
    t = datetime(2026, 10, 10, 13, tzinfo=timezone.utc)
    q = NS(starts_at=t, ends_at=t + timedelta(hours=1))
    r = NS(starts_at=t + timedelta(days=1), ends_at=t + timedelta(days=1, hours=2))
    assert race_mode([r, q], t - timedelta(hours=5)) == ("next", q)
    assert race_mode([r, q], t - timedelta(hours=2)) == ("countdown", q)
    assert race_mode([r, q], t + timedelta(minutes=5)) == ("live", q)
    assert race_mode([r, q], t + timedelta(minutes=100)) == ("results", q)
    assert race_mode([r, q], t + timedelta(hours=4)) == ("next", r)
    assert race_mode([q], t + timedelta(days=3)) == ("next", None)
    assert session_state(q.starts_at, q.ends_at, t - timedelta(minutes=10)) == "starting_soon"


def test_qualifying_timing_gaps_sectors_and_pit():
    st = SessionState(1)
    st.apply("drivers", [{"driver_number": 12, "name_acronym": "ANT", "team_colour": "00d7b6"},
                         {"driver_number": 1, "name_acronym": "VER", "team_colour": "4781d7"}])
    st.apply("position", [{"driver_number": 1, "position": 2, "date": "2026-10-10T13:20:00+00:00"},
                          {"driver_number": 12, "position": 1, "date": "2026-10-10T13:20:00+00:00"}])
    lap = lambda n, no, s1, s2, s3: {"driver_number": n, "lap_number": no, "date_start": "2026-10-10T13:10:00+00:00",
                                     "lap_duration": s1 + s2 + s3, "duration_sector_1": s1,
                                     "duration_sector_2": s2, "duration_sector_3": s3}
    st.apply("laps", [lap(12, 1, 30.0, 35.0, 30.0), lap(12, 2, 29.0, 35.5, 30.5), lap(1, 1, 29.5, 35.2, 30.4)])
    st.apply("pit", [{"driver_number": 1, "date": "2026-10-10T13:29:50+00:00", "lane_duration": None}])
    st.apply("race_control", [{"qualifying_phase": 3, "date": "2026-10-10T13:25:00+00:00"}])
    t = build_timing(st, "s", "QUALIFYING", 62, datetime(2026, 10, 10, 13, 30, tzinfo=timezone.utc))
    ant, ver = t["rows"]
    assert (t["phase"], t["lap"], t["laps_total"]) == ("Q3", None, None)
    assert (ant["code"], ant["time"], ant["gap"], ant["team_color"]) == ("ANT", "1:35.000", None, "00D7B6")
    assert (ver["time"], ver["gap"], ver["in_pit"]) == ("1:35.100", "+0.100", True)
    assert ant["sectors"] == ["purple", "yellow", "yellow"]  # S1 29.0 is session best; S2/S3 slower than lap 1


def test_endpoints():
    assert client.get("/api/races/next").json()["short_name"] == "SINGAPORE GP"
    assert client.get("/api/session/next").json()["state"] == "upcoming"
    assert [d["code"] for d in client.get("/api/standings/drivers").json()] == ["ANT", "VER"]
    assert client.get("/api/standings/constructors").json()[0]["short_name"] == "MERCEDES"
    d = client.get("/api/drivers/antonelli").json()
    assert (d["position"], d["podiums"], d["poles"], d["last5"]) == (1, 2, 2, [2, 1])
    assert client.get("/api/session/2026-16-race/timing").json()["rows"][1]["gap"] == "+2.307"
    assert client.get("/api/session/live").status_code == 204
    assert client.get("/api/status").json()["database"] == "sqlite"


def test_snapshot_modes():
    s = client.get("/api/widgets/snapshot", params={"driver": "antonelli"}).json()
    assert s["mode"] == "countdown" and s["next_session"]["type"] == "QUALIFYING"
    assert s["driver"]["code"] == "ANT" and s["race"]["laps_total"] == 62
    after_race = NOW - timedelta(days=2) + timedelta(hours=2, minutes=30)  # 30 min after round 16 ended
    snap = build_snapshot("antonelli", after_race)
    assert snap.mode == "results" and snap.results.rows[0].code == "VER"
    # The finished weekend stays current through the results window, with the driver's result attached.
    assert snap.race.round == 16 and [w.position for w in snap.driver.weekend if w.session_type == "RACE"] == [2]


def test_validation_auth_and_rate_limit():
    assert client.get("/api/races/99").status_code == 422
    assert client.get("/api/drivers/DROP TABLE").status_code == 422
    settings.api_key = "secret"
    try:
        assert client.get("/api/status").status_code == 401
        assert client.get("/api/status", headers={"X-API-Key": "secret"}).status_code == 200
    finally:
        settings.api_key = None
    settings.rate_limit_per_minute = 2
    try:
        from apex import main
        main._buckets.clear()
        codes = [client.get("/api/status").status_code for _ in range(3)]
        assert codes == [200, 200, 429]
        # Suffix tricks don't escape the limiter (/api/drivers/{id} with id="stream").
        assert client.get("/api/drivers/stream").status_code == 429
    finally:
        settings.rate_limit_per_minute = 120
        main._buckets.clear()
        cache.backend.delete_prefix("api:")


def test_external_colours_are_sanitised():
    """OpenF1 team colours reach HTML style attributes and native hex parsers: only RRGGBB passes."""
    assert safe_hex("00d7b6") == "00D7B6"
    for bad in ['"><img src=x onerror=alert(1)>', "red", "00D7B6;x", "", None, 123]:
        assert safe_hex(bad) is None
    st = SessionState(1)
    st.apply("drivers", [{"driver_number": 1, "name_acronym": "VER", "team_colour": '"><script>'}])
    st.apply("position", [{"driver_number": 1, "position": 1, "date": "2026-10-10T13:20:00+00:00"}])
    assert build_timing(st, "s", "RACE", 62, datetime(2026, 10, 10, 13, 30, tzinfo=timezone.utc))["rows"][0]["team_color"] is None


def test_live_cursors_reread_running_laps_and_ties():
    st = SessionState(1)
    st.apply("laps", [{"driver_number": 1, "lap_number": 4, "date_start": "2026-10-10T13:00:00+00:00", "lap_duration": 95.0},
                      {"driver_number": 1, "lap_number": 5, "date_start": "2026-10-10T13:01:35+00:00", "lap_duration": None}])
    assert st.cursor["laps"] == "2026-10-10T13:01:35+00:00"  # lap 5 is still running: read it again next poll
    st.apply("laps", [{"driver_number": 1, "lap_number": 5, "date_start": "2026-10-10T13:01:35+00:00", "lap_duration": 94.2}])
    assert st.laps[1][5]["lap_duration"] == 94.2


def test_qualifying_ranks_on_current_phase():
    st = SessionState(1)
    st.apply("drivers", [{"driver_number": 1, "name_acronym": "VER"}, {"driver_number": 4, "name_acronym": "NOR"}])
    st.apply("position", [{"driver_number": 1, "position": 1, "date": "2026-10-10T13:50:00+00:00"},
                          {"driver_number": 4, "position": 2, "date": "2026-10-10T13:50:00+00:00"}])
    st.apply("race_control", [{"qualifying_phase": 3, "date": "2026-10-10T13:40:00+00:00"}])
    lap = lambda n, no, t, d: {"driver_number": n, "lap_number": no, "date_start": t, "lap_duration": d}
    st.apply("laps", [lap(4, 3, "2026-10-10T13:20:00+00:00", 89.9),  # NOR's Q2 lap: quicker than anything in Q3
                      lap(1, 8, "2026-10-10T13:45:00+00:00", 90.0), lap(4, 9, "2026-10-10T13:45:30+00:00", 90.2)])
    ver, nor = build_timing(st, "s", "QUALIFYING", None, datetime(2026, 10, 10, 13, 50, tzinfo=timezone.utc))["rows"]
    assert (ver["time"], nor["time"], nor["gap"]) == ("1:30.000", "1:30.200", "+0.200")


def test_postgres_style_aware_datetimes_come_back_in_utc():
    from apex.models import UTCDateTime
    berlin = datetime(2026, 10, 4, 14, tzinfo=timezone(timedelta(hours=2)))
    assert UTCDateTime().process_result_value(berlin, None).utcoffset() == timedelta(0)


def test_teams_list_only_this_seasons_drivers():
    with SessionLocal() as db:  # a 2025 driver still pointing at the team must not appear
        db.add(Driver(id="old_hand", code="OLD", first_name="Old", last_name="Hand", team_id="red_bull"))
        db.commit()
    assert client.get("/api/teams/red_bull").json()["drivers"] == ["max_verstappen"]


def test_background_loops_survive_crashes():
    import asyncio

    from apex.main import supervised
    calls = []

    async def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("db blip")
        raise asyncio.CancelledError

    async def run():
        sleeps = asyncio.sleep
        asyncio.sleep = lambda _: sleeps(0)  # skip the 30 s back-off
        try:
            await supervised("test", flaky)
        except asyncio.CancelledError:
            pass
        finally:
            asyncio.sleep = sleeps

    asyncio.run(run())
    assert len(calls) == 2  # crashed once, restarted, then stopped on cancel


def test_unconfirmed_session_times_are_not_scheduled():
    from apex.ingest import _dt
    assert _dt({"date": "2026-11-01"}) is None
    assert _dt({"date": "2026-11-01", "time": "14:00:00Z"}).hour == 14


def test_driver_silhouette_in_team_colour(monkeypatch):
    import io

    from PIL import Image

    from apex import portraits
    photo = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    photo.paste((200, 150, 120, 255), (2, 2, 6, 8))  # an opaque "driver" on a transparent background
    buf = io.BytesIO()
    photo.save(buf, "PNG")
    monkeypatch.setattr(portraits, "_download", lambda url: buf.getvalue())
    portraits._render.cache_clear()
    cache.set_json(portraits.DRIVERS_KEY, {
        "ANT": {"number": 12, "headshot": "https://media.formula1.com/x/andant01.png.transform/1col/image.png"},
        "VER": {"number": 3, "headshot": "https://evil.example/ver.png"}}, 60)

    r = client.get("/api/drivers/antonelli/silhouette.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    img = Image.open(io.BytesIO(r.content))
    assert img.getpixel((3, 4)) == (0x00, 0xD7, 0xB6, 255)  # Mercedes teal where the driver is
    assert img.getpixel((0, 0))[3] == 0                      # still transparent around them
    assert client.get("/api/drivers/max_verstappen/silhouette.png").status_code == 404  # non-F1 host: refused
    assert client.get("/api/drivers/antonelli").json()["race_number"] == 12
    assert client.get("/api/drivers/antonelli/silhouette.png", params={"size": 206}).status_code == 200
    assert client.get("/api/drivers/antonelli/silhouette.png", params={"size": 5000}).status_code == 422
