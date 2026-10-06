from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Numeric, String, TypeDecorator, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import settings

SESSION_TYPES = ("FP1", "FP2", "FP3", "SPRINT_QUALIFYING", "SPRINT", "QUALIFYING", "RACE")


class UTCDateTime(TypeDecorator):
    """TIMESTAMPTZ on PostgreSQL; SQLite drops the zone, so re-attach UTC on read."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return value.astimezone(timezone.utc) if value else value

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        # SQLite drops the zone; PostgreSQL returns the server's TimeZone. Either way, hand back UTC.
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class Base(DeclarativeBase):
    pass


class Team(Base):
    __tablename__ = "teams"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str]
    nationality: Mapped[str | None]
    color: Mapped[str | None] = mapped_column(String(6))


class Driver(Base):
    __tablename__ = "drivers"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    code: Mapped[str] = mapped_column(String(3))
    number: Mapped[int | None]
    first_name: Mapped[str]
    last_name: Mapped[str]
    nationality: Mapped[str | None]
    country_code: Mapped[str | None] = mapped_column(String(2))
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id"))


class Race(Base):
    __tablename__ = "races"
    season: Mapped[int] = mapped_column(primary_key=True)
    round: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    circuit_id: Mapped[str]
    circuit_name: Mapped[str]
    locality: Mapped[str | None]
    country: Mapped[str | None]
    country_code: Mapped[str | None] = mapped_column(String(2))
    laps_total: Mapped[int | None]


class Session(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        ForeignKeyConstraint(["season", "round"], ["races.season", "races.round"]),
        CheckConstraint(f"type IN {SESSION_TYPES}", name="session_type"),
    )
    id: Mapped[str] = mapped_column(String, primary_key=True)
    season: Mapped[int]
    round: Mapped[int]
    type: Mapped[str]
    starts_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    ends_at: Mapped[datetime] = mapped_column(UTCDateTime)


class DriverStanding(Base):
    __tablename__ = "driver_standings"
    season: Mapped[int] = mapped_column(primary_key=True)
    driver_id: Mapped[str] = mapped_column(ForeignKey("drivers.id"), primary_key=True)
    position: Mapped[int]
    points: Mapped[float] = mapped_column(Numeric(6, 1, asdecimal=False))
    wins: Mapped[int]


class ConstructorStanding(Base):
    __tablename__ = "constructor_standings"
    season: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), primary_key=True)
    position: Mapped[int]
    points: Mapped[float] = mapped_column(Numeric(6, 1, asdecimal=False))
    wins: Mapped[int]


class Result(Base):
    __tablename__ = "results"
    season: Mapped[int] = mapped_column(primary_key=True)
    round: Mapped[int] = mapped_column(primary_key=True)
    session_type: Mapped[str] = mapped_column(primary_key=True)
    driver_id: Mapped[str] = mapped_column(ForeignKey("drivers.id"), primary_key=True)
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id"))
    position: Mapped[int | None]
    grid: Mapped[int | None]
    points: Mapped[float | None] = mapped_column(Numeric(6, 1, asdecimal=False))
    gap: Mapped[str | None]
    status: Mapped[str | None]


engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)
