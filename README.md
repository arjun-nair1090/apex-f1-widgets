# APEX

> The F1 data layer that lives everywhere.

APEX is a set of glanceable F1 widgets for iOS, Android and Windows, plus the backend that feeds them. The widgets are
the product. The companion apps only configure and preview them.

Built from [`APEX_F1_Widget_Master_Prompt.md`](APEX_F1_Widget_Master_Prompt.md). Start with
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and [`docs/DESIGN_SYSTEM.md`](docs/DESIGN_SYSTEM.md).

| Folder | What | State |
|---|---|---|
| `backend/` | FastAPI + SQLAlchemy + Redis/memory cache, Jolpica ingest, OpenF1 live timing, SSE, web preview | runs, tests pass |
| `ios/` | SwiftUI + WidgetKit (9 widgets, lock screen), App Intents, Live Activity + Dynamic Island | source; needs Xcode |
| `android/` | Kotlin, Jetpack Glance (9 responsive widgets), WorkManager, Material 3 app | builds, lint clean |
| `windows/` | Windows App SDK Widgets Board provider (COM) + Adaptive Cards, WinUI companion window | builds |
| `shared/` | design tokens, brand marks, OpenAPI schema | — |

## Backend + web preview

```sh
cd backend
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # .venv/bin on macOS/Linux
.venv/Scripts/python -m uvicorn apex.main:app --port 8077
.venv/Scripts/python -m pytest -q
```

Open http://localhost:8077 to see the widget preview: every widget at every size, live data, the platform and theme
switches, and simulated situations (lights out, live race, live quali, results, offline, live data unavailable, loading).

Configure with env vars (see `backend/.env.example`). Leave them unset and it runs on SQLite with an in-memory cache.

| Var | Purpose |
|---|---|
| `DATABASE_URL` | `postgresql+psycopg://…` in production |
| `REDIS_URL` | shared cache when running several workers |
| `OPENF1_TOKEN` | paid OpenF1 key, **required for real-time timing during sessions** (historical data is free) |
| `API_KEY` | when set, every `/api` call needs `X-API-Key` |
| `EXTRA_SEASONS` | e.g. `2025`: past seasons for the Driver widget's season option |
| `BACKGROUND_JOBS` | `0` on every replica but one, so only one process polls Jolpica and OpenF1 |

Behind a reverse proxy, start uvicorn with `--forwarded-allow-ips=<proxy ip>` so rate limiting sees real client IPs
rather than the proxy's.

Regenerate the API contract after schema changes:
`python -c "import json; from apex.main import app; json.dump(app.openapi(), open('../shared/api-schema/openapi.json','w'), indent=1)"`

## Android

```sh
cd android
./gradlew assembleDebug -PapexBaseUrl=https://your-backend   # default http://10.0.2.2:8077 (emulator → host)
```

Needs the Android SDK (compileSdk 37) and JDK 17+. Install the APK, open APEX to pick a driver and style, then use
**Add to home screen** or the launcher's widget picker.

## Windows

```sh
cd windows/APEX
dotnet build -p:Platform=x64 -p:ApexBaseUrl=https://your-backend
```

The provider only appears on the Widgets Board when installed as an MSIX: turn on Developer Mode, deploy the package
(Visual Studio *Deploy*, or `dotnet build -p:GenerateAppxPackageOnBuild=true` then install the `.msix`), then press
Win + W → Add widgets → APEX. Each widget's menu → **Customize** sets its driver and information density.

Debug without the board: `APEX.exe -DumpCards <dir> [driver]` writes the exact template and data every widget would
get, at every size.

## iOS

```sh
cd ios
brew install xcodegen && xcodegen      # → APEX.xcodeproj
```

Set your team in `project.yml`, register the App Group `group.club.apex`, and set `APEX_BASE_URL`. The app and the
widget extension share the snapshot cache and preferences through the App Group.
