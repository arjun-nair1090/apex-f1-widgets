# APEX — Architecture

> The F1 data layer that lives everywhere.

Covers spec §39 deliverables 1, 5, 6, 7, 8, 9: product architecture, backend architecture,
database schema, API specification, folder structure, roadmap. Design system, brand and widget
specs live in [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md).

---

## 1. Product architecture

The widgets are the product. The companion apps exist to configure and preview them.

```text
                    ┌────────────── backend (one deploy) ──────────────┐
 Jolpica (Ergast) ─▶│ ingest ─▶ normalize ─▶ PostgreSQL                 │
   schedule,        │                          │                        │
   standings,       │                          ▼                        │
   results          │                    Redis cache ◀─ live processor ◀── OpenF1
                    │                          │          (live only)   │   positions, gaps,
                    │                          ▼                        │   laps, pits
                    │                       FastAPI ── REST + SSE       │
                    └──────────────────────────┬────────────────────────┘
                                               │  GET /api/widgets/snapshot  (one call per refresh)
               ┌───────────────────────────────┼───────────────────────────────┐
               ▼                               ▼                               ▼
     iOS: WidgetKit timelines       Android: Glance + WorkManager     Windows: Widget Board provider
     Live Activity / Dynamic Island  Material 3 companion app          (Adaptive Cards) + WinUI app
```

### Key decisions

| Decision | Why |
|---|---|
| **One snapshot endpoint for widgets** (`/api/widgets/snapshot`) | A widget refresh is one request, not six. Battery and network are the top performance priorities (spec §29). The granular endpoints stay for the apps and third parties. |
| **Race Mode is computed on the client from session times** | Widgets must flip *Countdown → LIVE* at the start time without a network request (spec §8). WidgetKit/Glance timelines get an entry at each boundary. The server also returns `mode` as a hint. |
| **Live timing pushes via SSE, widgets refresh via timelines** | OS widget processes cannot hold sockets. The apps and Live Activities use the SSE stream. Home-screen widgets get budgeted reloads (iOS) or a 1-minute Glance refresh while a session is live (Android). |
| **Never-empty widgets** | Every client persists the last snapshot to disk and renders it with `LAST UPDATED 2m AGO` when the network fails (spec §23). |
| **Session-start notifications are scheduled locally** | Start times are known days ahead, so no push infrastructure is needed. Result notifications fire from the background refresh when a new result for the favourite driver appears. |

### Race Mode (spec §15)

Evaluated per timeline entry with `now`:

```text
any session where start ≤ now < end         → LIVE      (live timing)
a session ended less than 90 min ago        → RESULTS   (that session's classification)
next session starts within 3 h              → COUNTDOWN
otherwise                                   → NEXT      (next session card)
```

Session state: `upcoming` → `starting_soon` (T-15 min) → `live` → `finished`.
End times come from OpenF1 when known, otherwise nominal durations
(FP 60, Sprint Quali 45, Sprint 60, Quali 60, Race 120 minutes).

---

## 2. Backend architecture

```text
backend/apex/
  config.py      env-driven settings (no secrets in code)
  models.py      SQLAlchemy tables (PostgreSQL in prod, SQLite for local dev)
  schemas.py     Pydantic response models = the API contract
  cache.py       Redis when REDIS_URL is set, in-process TTL dict otherwise
  ingest.py      Jolpica → normalize → upsert (schedule, standings, results)
  live.py        OpenF1 live processor → timing snapshot → cache + SSE fan-out
  racemode.py    session state + Race Mode rules (mirrored in each client)
  api.py         routes, validation, auth, rate limiting
  main.py        app + background loops
```

**Ingestion cadence.** Full schedule and standings sync on startup and every 30 min.
Jolpica allows ~4 req/s, so that is nowhere near its limit. Results are re-pulled every 5 min for
two hours after a session ends, which is when they change.

**Live processor.** Wakes when Race Mode says LIVE. Polls OpenF1 every `LIVE_POLL_SECONDS` (default 4)
using `date>` filters, so each poll only pulls new rows. It merges positions, intervals, laps and
pits into one `Timing` snapshot, writes it to the cache (TTL 10 min) and pushes it to SSE
subscribers only when something changed. It sleeps outside live sessions, so the data source sees
zero traffic.

> OpenF1 serves historical data free. Real-time data during a session needs a paid key
> (`OPENF1_TOKEN`). Without one, the live processor reports `live_unavailable` and the widgets fall
> back to the cached state with "LIVE DATA UNAVAILABLE", per spec §34.

**DRS.** The 2026 regulations removed DRS, so the API reports `drs: null`.
The field stays in the schema so the client renders it as soon as a source provides it.

**Security (spec §30).** All configuration comes from env vars (`.env.example`). Optional `API_KEY`
requires an `X-API-Key` header. A per-IP token-bucket rate limiter is applied. Path params are typed and
range-checked. TLS terminates at the reverse proxy or platform, and the app sets HSTS when
`FORCE_HTTPS=1`.

---

## 3. Database schema

```sql
CREATE TABLE teams (
  id           TEXT PRIMARY KEY,          -- jolpica constructorId, e.g. 'mclaren'
  name         TEXT NOT NULL,
  nationality  TEXT,
  color        CHAR(6)                    -- from OpenF1 team_colour, hex without '#'
);

CREATE TABLE drivers (
  id            TEXT PRIMARY KEY,         -- jolpica driverId, e.g. 'max_verstappen'
  code          CHAR(3) NOT NULL,         -- 'VER'
  number        INTEGER,
  first_name    TEXT NOT NULL,
  last_name     TEXT NOT NULL,
  nationality   TEXT,
  country_code  CHAR(2),                  -- ISO-3166 alpha-2, for flags
  team_id       TEXT REFERENCES teams(id)
);

CREATE TABLE races (
  season        INTEGER NOT NULL,
  round         INTEGER NOT NULL,
  name          TEXT NOT NULL,            -- 'Singapore Grand Prix'
  circuit_id    TEXT NOT NULL,
  circuit_name  TEXT NOT NULL,
  locality      TEXT,
  country       TEXT,
  country_code  CHAR(2),
  laps_total    INTEGER,                  -- previous edition's distance until the race is run
  PRIMARY KEY (season, round)
);

CREATE TABLE sessions (
  id          TEXT PRIMARY KEY,           -- '2026-17-qualifying'
  season      INTEGER NOT NULL,
  round       INTEGER NOT NULL,
  type        TEXT NOT NULL CHECK (type IN ('FP1','FP2','FP3','SPRINT_QUALIFYING','SPRINT','QUALIFYING','RACE')),
  starts_at   TIMESTAMPTZ NOT NULL,
  ends_at     TIMESTAMPTZ NOT NULL,
  FOREIGN KEY (season, round) REFERENCES races(season, round)
);
CREATE INDEX sessions_starts_at ON sessions (starts_at);

CREATE TABLE driver_standings (
  season     INTEGER NOT NULL,
  driver_id  TEXT NOT NULL REFERENCES drivers(id),
  position   INTEGER NOT NULL,
  points     NUMERIC(6,1) NOT NULL,
  wins       INTEGER NOT NULL,
  PRIMARY KEY (season, driver_id)
);

CREATE TABLE constructor_standings (
  season    INTEGER NOT NULL,
  team_id   TEXT NOT NULL REFERENCES teams(id),
  position  INTEGER NOT NULL,
  points    NUMERIC(6,1) NOT NULL,
  wins      INTEGER NOT NULL,
  PRIMARY KEY (season, team_id)
);

CREATE TABLE results (
  season        INTEGER NOT NULL,
  round         INTEGER NOT NULL,
  session_type  TEXT NOT NULL,            -- 'RACE' | 'SPRINT' | 'QUALIFYING'
  driver_id     TEXT NOT NULL REFERENCES drivers(id),
  team_id       TEXT REFERENCES teams(id),
  position      INTEGER,                  -- NULL = not classified
  grid          INTEGER,
  points        NUMERIC(6,1),
  gap           TEXT,                     -- '+8.221', '+1 Lap', or best quali time
  status        TEXT,
  PRIMARY KEY (season, round, session_type, driver_id)
);
```

The SQLAlchemy models in `backend/apex/models.py` are the source of truth. `create_all` builds this
schema on PostgreSQL and on SQLite. Podiums, poles and the last five results are derived from
`results`, so they can't drift from the source data.

---

## 4. API specification

Base: `/api`. JSON, UTF-8, ISO-8601 UTC timestamps. The machine-readable contract is
[`shared/api-schema/openapi.json`](../shared/api-schema/openapi.json), generated from the
FastAPI app.

| Method | Path | Returns | Cache TTL |
|---|---|---|---|
| GET | `/api/season/current` | `Season`: year, round count, next round | 5 min |
| GET | `/api/races` | `Race[]` with sessions | 5 min |
| GET | `/api/races/{round}` | `Race` (1 ≤ round ≤ 30) | 5 min |
| GET | `/api/races/next` | `Race`: current weekend, or the next one | 1 min |
| GET | `/api/session/next` | `Session`: next not-finished session | 1 min |
| GET | `/api/session/live` | `Timing`, or 204 if nothing is live | live |
| GET | `/api/session/live/stream` | SSE: `event: timing` on every change, plus a heartbeat every 15 s | — |
| GET | `/api/session/{id}/timing` | `Timing` (live, or the final cached classification) | 10 min |
| GET | `/api/standings/drivers` | `DriverStanding[]` | 5 min |
| GET | `/api/standings/constructors` | `ConstructorStanding[]` | 5 min |
| GET | `/api/drivers` | `Driver[]` | 5 min |
| GET | `/api/drivers/{id}` | `DriverDetail`: stats, last 5, this weekend | 1 min |
| GET | `/api/teams` | `Team[]` | 5 min |
| GET | `/api/teams/{id}` | `Team` with drivers | 5 min |
| GET | `/api/status` | `Status`: data source health, last sync, cache backend | none |
| GET | `/api/widgets/snapshot?driver={id}` | `WidgetSnapshot`: everything a widget needs | 30 s |

Errors use `{"detail": "..."}` with 401 (bad API key), 404, 422 (validation) or 429 (rate limited, with
`Retry-After`). Stack traces never reach clients.

### `WidgetSnapshot`

```jsonc
{
  "generated_at": "2026-10-10T12:58:00Z",
  "mode": "countdown",                       // live | results | countdown | next
  "race": { "season": 2026, "round": 17, "name": "Singapore Grand Prix", "short_name": "SINGAPORE GP",
            "country_code": "SG", "laps_total": 62, "sessions": [ /* Session */ ] },
  "next_session": { "id": "2026-17-qualifying", "type": "QUALIFYING", "label": "QUALIFYING",
                    "starts_at": "...", "ends_at": "...", "state": "starting_soon" },
  "live": null,                              // Timing when a session is running
  "results": null,                           // Timing (final) when mode = results
  "drivers": [ /* top-10 DriverStanding */ ],
  "constructors": [ /* top-10 ConstructorStanding */ ],
  "driver": { /* DriverDetail for ?driver= */ },
  "live_unavailable": false
}
```

### `Timing`

```jsonc
{
  "session_id": "2026-17-race", "session_type": "RACE", "phase": null,   // "Q1".."Q3" in qualifying
  "lap": 42, "laps_total": 62, "final": false, "updated_at": "...",
  "rows": [
    { "position": 1, "driver_number": 12, "code": "ANT", "team_color": "27F4D2",
      "time": "1:38.589",   // best lap (qualifying/practice) or last lap (race)
      "gap": null,          // to leader: "+1.824", "+1 LAP"
      "interval": null,     // to car ahead
      "sectors": ["purple", "green", "yellow"],   // last lap; null when unknown
      "in_pit": false, "drs": null }
  ]
}
```

---

## 5. Folder structure

```text
/backend
    /apex            FastAPI app (api, models, schemas, cache, ingest, live)
    /apex/preview    web widget preview / design reference (served at /)
    /tests           pytest, offline fixtures
/ios
    /APEX            companion app (SwiftUI): configure + preview
    /Shared          tokens, models, API client, Race Mode: shared by app and extension
    /Widgets         WidgetKit extension
    /LiveActivities  ActivityKit attributes + Dynamic Island
    project.yml      XcodeGen spec
/android
    /app             Kotlin, Compose (Material 3) companion app + Glance widgets
/windows
    /APEX            WinUI 3 companion app + Widget Board provider (COM)
    /APEX/Widgets    Adaptive Card templates
/shared
    /design-tokens   tokens.json: the single source for every platform
    /brand           APEX mark + wordmark SVGs
    /api-schema      openapi.json (generated)
/docs
```

---

## 6. Roadmap

| Phase | Scope | Status |
|---|---|---|
| 1 | Design system + branding | ✅ tokens, brand marks, widget specs, web preview (`/`) |
| 2 | Backend + data ingestion | ✅ Jolpica ingest checked against live 2026 data; PostgreSQL/SQLite; Redis/memory cache; `pytest` passes |
| 3 | API | ✅ all spec endpoints + `/api/widgets/snapshot`, OpenAPI export; `?season=` on driver endpoints (`EXTRA_SEASONS`) |
| 4 | iOS widgets | 🟡 source complete (9 widgets, lock screen, Live Activity + Dynamic Island, App Intents) but **not compiled**: needs Xcode on macOS |
| 5 | Android widgets | ✅ 9 Glance widgets + Material 3 app; `assembleDebug` builds and `lintDebug` has 0 errors; not run on a device |
| 6 | Windows widgets | ✅ Widgets Board COM provider + 7 Adaptive Card templates; builds clean; all 27 widget×size payloads (plus live state) rendered with the Adaptive Cards renderer via `APEX.exe -DumpCards <dir> [driver]`; MSIX not yet deployed to a board |
| 7 | Real-time timing | ✅ OpenF1 live processor (replayed on a real race), SSE (paid key required during sessions) |
| 8 | Notifications | ✅ local session-start alerts, favourite driver result/podium on refresh, opt-in live progress (Android) |
| 9 | Customization | ✅ driver, team, density, theme, accent; live preview (web, iOS app, Android app via real RemoteViews) |
| 10 | Performance + polish | ⏳ device profiling, Live Activity push via APNs, store assets |

**Next, in order of value:** APNs push for Live Activities (remote updates at lap cadence instead of
the in-app SSE bridge), Redis pub/sub for multi-instance SSE, and track status (SC/VSC/red flag) from
OpenF1 race control.
