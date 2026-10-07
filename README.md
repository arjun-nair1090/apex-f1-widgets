# APEX

> The F1 data layer that lives everywhere.

APEX is a set of glanceable F1 widgets for iOS, Android, Windows and Linux, plus the backend that feeds them. The widgets are
the product. The companion apps only configure and preview them.

Built from [`APEX_F1_Widget_Master_Prompt.md`](APEX_F1_Widget_Master_Prompt.md). Start with
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and [`docs/DESIGN_SYSTEM.md`](docs/DESIGN_SYSTEM.md).

| Folder | What | State |
|---|---|---|
| `backend/` | FastAPI + SQLAlchemy + Redis/memory cache, Jolpica ingest, OpenF1 live timing, SSE, web preview | runs, tests pass |
| `ios/` | SwiftUI + WidgetKit (9 widgets, lock screen), App Intents, Live Activity + Dynamic Island | source; needs Xcode |
| `android/` | Kotlin, Jetpack Glance (9 responsive widgets), WorkManager, Material 3 app | builds, lint clean |
| `windows/` | Windows App SDK Widgets Board provider (COM) + Adaptive Cards, WinUI companion window | builds |
| `linux/` | GTK 3 + WebKit2GTK desktop widgets (layer-shell on Wayland) and APEX app | runs on Hyprland |
| `shared/` | design tokens, brand marks, OpenAPI schema | — |

## Backend + web preview

```sh
cd backend
python -m venv .venv && .venv/bin/pip install -r requirements.txt   # .venv/Scripts on Windows
.venv/bin/python -m uvicorn apex.main:app --port 8077
.venv/bin/python -m pytest -q
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

Open **APEX** from the Start menu to pick your driver (cards show each driver's silhouette and number), browse every
widget as a live preview and add it to the desktop in one click. The **Circuit** widget, and the space in Next
session and Countdown, show the upcoming track in 3D, built from a real lap of an earlier race there
(`GET /api/races/{round}/track`; new circuits get a map after their first race). Re-run the script after pulling changes; it installs each build as a package update, so pinned widgets stay.

Debug without the board: `APEX.exe -DumpCards <dir> [driver]` writes the exact template and data every widget would
get, at every size. WinUI crashes are logged to `%LOCALAPPDATA%\APEX\crash.log`.

## Linux

The same desktop widgets and APEX app as on Windows, for GTK desktops. Install the system packages first. They come
from your distro, not pip, because the client runs on the system Python:

```sh
sudo pacman -S python-gobject gtk3 webkit2gtk-4.1 gtk-layer-shell                              # Arch
sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-webkit2-4.1 gir1.2-gtklayershell-0.1         # Debian/Ubuntu
sudo dnf install python3-gobject gtk3 webkit2gtk4.1 gtk-layer-shell                            # Fedora
```

Then one script does the rest: the data server as a systemd user service (`apex-backend`, now and at every login,
logs in `backend/apex.log`), the `apex` command in `~/.local/bin`, **APEX** in your app menu, and the desktop
widgets, started now and at login. Re-run it after pulling changes.

```sh
linux/install.sh
```

- **Desktop:** frameless F1-style widgets on the right edge of the screen (Race Mode and your favourite driver to
  start). Drag to move, right-click to resize or remove. Add more from the **APEX** app (`apex`).
- **Wayland with layer-shell (Hyprland, sway, KDE Plasma):** widgets sit on the bottom layer, under your windows and
  outside tiling. They use the layer namespace `apex-widget` for compositor rules. Hyprland and sway don't run
  autostart entries, so add `exec-once = ~/.local/bin/apex --desktop` (Hyprland) or `exec ~/.local/bin/apex --desktop`
  (sway) to your config.
- **X11:** widgets are undecorated windows kept below the others and on every workspace.
- **GNOME on Wayland:** there's no layer-shell, so widgets are ordinary undecorated windows that GNOME places and
  stacks itself.
- There is no Widgets board or lock screen on Linux, so the app hides that section.

Settings are in `~/.local/share/APEX` (`desktop.json` and `defaults.json`, the same format as on Windows), and
crashes are logged to `crash.log` there. Run `apex --desktop` or `apex` from a terminal to see errors.
`APEX_BASE_URL` points the client at another server. Unit tests: `cd linux && python3 -m pytest tests`.

## iOS

```sh
cd ios
brew install xcodegen && xcodegen      # → APEX.xcodeproj
```

Set your team in `project.yml`, register the App Group `group.club.apex`, and set `APEX_BASE_URL`. The app and the
widget extension share the snapshot cache and preferences through the App Group.
