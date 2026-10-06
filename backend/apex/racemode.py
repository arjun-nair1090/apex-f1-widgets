"""Session state + Race Mode (docs/ARCHITECTURE.md §1). Mirrored in RaceMode.swift / RaceMode.kt / RaceMode.cs."""

from datetime import datetime, timedelta

SOON = timedelta(minutes=15)
RESULTS_WINDOW = timedelta(minutes=90)
COUNTDOWN_WINDOW = timedelta(hours=3)

DURATION_MIN = {"FP1": 60, "FP2": 60, "FP3": 60, "SPRINT_QUALIFYING": 45, "SPRINT": 60, "QUALIFYING": 60, "RACE": 120}
LABEL = {"FP1": "FP1", "FP2": "FP2", "FP3": "FP3", "SPRINT_QUALIFYING": "SPRINT QUALI", "SPRINT": "SPRINT",
         "QUALIFYING": "QUALIFYING", "RACE": "RACE"}


def session_state(starts_at: datetime, ends_at: datetime, now: datetime) -> str:
    if now >= ends_at:
        return "finished"
    if now >= starts_at:
        return "live"
    if now >= starts_at - SOON:
        return "starting_soon"
    return "upcoming"


def race_mode(sessions, now: datetime) -> tuple[str, object | None]:
    """sessions: objects with .starts_at/.ends_at, any order. Returns (mode, the session it is about)."""
    ordered = sorted(sessions, key=lambda s: s.starts_at)
    for s in ordered:
        if s.starts_at <= now < s.ends_at:
            return "live", s
    ended = [s for s in ordered if s.ends_at <= now]
    if ended and now - ended[-1].ends_at < RESULTS_WINDOW:
        return "results", ended[-1]
    upcoming = next((s for s in ordered if s.starts_at > now), None)
    if upcoming is None:
        return "next", None
    return ("countdown" if upcoming.starts_at - now <= COUNTDOWN_WINDOW else "next"), upcoming

