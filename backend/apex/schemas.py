"""API contract. Exported to shared/api-schema/openapi.json; every client's Models mirror these."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

SessionType = Literal["FP1", "FP2", "FP3", "SPRINT_QUALIFYING", "SPRINT", "QUALIFYING", "RACE"]
SessionState = Literal["upcoming", "starting_soon", "live", "finished"]
Mode = Literal["live", "results", "countdown", "next"]
Sector = Literal["purple", "green", "yellow"]


class Session(BaseModel):
    id: str
    round: int
    type: SessionType
    label: str
    starts_at: datetime
    ends_at: datetime
    state: SessionState


class Race(BaseModel):
    season: int
    round: int
    name: str
    short_name: str
    circuit_name: str
    locality: str | None
    country: str | None
    country_code: str | None
    laps_total: int | None
    sessions: list[Session]


class Season(BaseModel):
    year: int
    rounds: int
    next_round: int | None


class Team(BaseModel):
    id: str
    name: str
    short_name: str
    color: str | None
    nationality: str | None
    drivers: list[str] = []


class Driver(BaseModel):
    id: str
    code: str
    number: int | None
    first_name: str
    last_name: str
    nationality: str | None
    country_code: str | None
    team_id: str | None
    team_name: str | None
    team_color: str | None


class DriverStanding(BaseModel):
    position: int
    driver_id: str
    code: str
    name: str
    team_id: str | None
    team_name: str | None
    team_color: str | None
    points: float
    wins: int


class ConstructorStanding(BaseModel):
    position: int
    team_id: str
    name: str
    short_name: str
    color: str | None
    points: float
    wins: int


class WeekendResult(BaseModel):
    session_type: SessionType
    position: int | None
    gap: str | None


class DriverDetail(Driver):
    race_number: int | None = None  # number on the car this season (the champion runs #1); `number` is permanent
    season: int
    position: int | None
    points: float
    wins: int
    podiums: int
    poles: int
    last5: list[int | None]  # most recent first; None = DNF/not classified
    weekend: list[WeekendResult]  # this race weekend's classified sessions, in order


class TimingRow(BaseModel):
    position: int
    driver_number: int
    code: str
    team_color: str | None
    time: str | None
    gap: str | None
    interval: str | None
    sectors: list[Sector | None] | None
    in_pit: bool
    drs: bool | None


class Timing(BaseModel):
    session_id: str
    session_type: SessionType
    phase: str | None
    lap: int | None
    laps_total: int | None
    final: bool
    updated_at: datetime
    rows: list[TimingRow]


class SourceStatus(BaseModel):
    ok: bool
    last_success: datetime | None
    error: str | None = None


class Status(BaseModel):
    ok: bool
    database: str
    cache: str
    live: bool
    live_unavailable: bool
    sources: dict[str, SourceStatus]
    now: datetime


class WidgetSnapshot(BaseModel):
    generated_at: datetime
    mode: Mode
    race: Race | None
    next_session: Session | None
    live: Timing | None
    results: Timing | None
    drivers: list[DriverStanding]
    constructors: list[ConstructorStanding]
    driver: DriverDetail | None
    live_unavailable: bool
