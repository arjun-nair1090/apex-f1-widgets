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

One script does everything on your PC: builds the app, registers its widgets with the Widgets board, and runs the
data server now and at every logon (hidden, logs in `backend/apex.log`). Turn on **Developer Mode** first
(Settings → System → Advanced), then:

```powershell
powershell -ExecutionPolicy Bypass -File windows\install.ps1
```

You get APEX in three places:

- **Desktop:** frameless F1-style widgets on the right edge of the screen (Race Mode and your favourite driver to
  start). Drag to move, right-click to resize or remove. Add more from the **APEX** app (Start menu → On your desktop).
  They start at every logon.
- **Widgets board:** Win + W → + (Add widgets) → APEX. Each widget's menu → **Customize** sets its driver and density.
- **Lock screen:** Settings → Personalization → Lock screen → Widgets → add an APEX widget (small ones fit there).

The board and lock screen show a picture of the same widget the desktop shows (taken by an offscreen WebView2 at
the board's tile size, refreshed when its data changes, at most once a minute). If the data server can't be reached
they fall back to plain text cards.

Open **APEX** from the Start menu to pick your driver (cards show each driver's silhouette and number), browse every
widget as a live preview and add it to the desktop in one click. The **Circuit** widget, and the space in Next
session and Countdown, show the upcoming track in 3D, built from a real lap of an earlier race there
(`GET /api/races/{round}/track`; new circuits get a map after their first race). Re-run the script after pulling changes; it installs each build as a package update, so pinned widgets stay.

Debug without the board: `APEX.exe -DumpImages <dir> [driver]` writes the picture every widget would show, at every
size; `APEX.exe -DumpCards <dir> [driver]` writes the text-card fallback (template and data).
After changing how the widgets look, refresh the **Add widgets** previews: `APEX.exe -DumpImages <dir> max_verstappen`,
then `backend\.venv\Scripts\python windows\screenshots.py <dir>`, and re-run the install script. WinUI crashes are logged to `%LOCALAPPDATA%\APEX\crash.log`.

## iOS

```sh
cd ios
brew install xcodegen && xcodegen      # → APEX.xcodeproj
```

Set your team in `project.yml`, register the App Group `group.club.apex`, and set `APEX_BASE_URL`. The app and the
widget extension share the snapshot cache and preferences through the App Group.
