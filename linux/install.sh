#!/usr/bin/env bash
# Installs APEX on this Linux desktop: the data server as a systemd user service (now and at every login), the APEX
# app in your app menu, and the desktop widgets (now and at every login). Safe to re-run after pulling changes.
# Needs Python 3.12+ and the GTK/WebKit packages it names if they're missing. Never runs sudo itself.
#
#   linux/install.sh
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
backend="$root/backend"
data_home=${XDG_DATA_HOME:-$HOME/.local/share}
config_home=${XDG_CONFIG_HOME:-$HOME/.config}

# 0. Requirements. The client runs on the system Python, because PyGObject and WebKit come from the distro.
python3 -c 'import sys; sys.exit(sys.version_info < (3, 12))' || { echo "APEX needs Python 3.12+." >&2; exit 1; }
if ! python3 -c 'import gi; gi.require_version("Gtk", "3.0"); gi.require_version("WebKit2", "4.1")' 2>/dev/null; then
    (cd "$root/linux" && python3 -m apexlinux) || true  # prints the packages to install for each distro
    exit 1
fi
if ! python3 -c 'import gi; gi.require_version("GtkLayerShell", "0.1")' 2>/dev/null && [ "${XDG_SESSION_TYPE:-}" = wayland ]; then
    echo "Note: gtk-layer-shell is not installed; on Hyprland, sway or KDE widgets will be ordinary windows." >&2
fi

# 1. Data server: venv on first run, then a user service (serve.pyw logs to backend/apex.log, as on Windows).
if [ ! -d "$backend/.venv" ]; then
    python3 -m venv "$backend/.venv"
    "$backend/.venv/bin/python" -m pip install -q -r "$backend/requirements.txt"
fi
mkdir -p "$config_home/systemd/user"
cat > "$config_home/systemd/user/apex-backend.service" <<EOF
[Unit]
Description=APEX F1 widgets data server on http://localhost:8077

[Service]
WorkingDirectory=$backend
ExecStart=$backend/.venv/bin/python serve.pyw
Restart=on-failure
RestartSec=60

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user enable -q apex-backend.service
systemctl --user restart apex-backend.service  # picks up pulled changes

# 2. The `apex` command, the app-menu entry and login autostart for the desktop widgets.
mkdir -p "$HOME/.local/bin" "$data_home/applications" "$config_home/autostart"
cat > "$HOME/.local/bin/apex" <<EOF
#!/bin/sh
PYTHONPATH="$root/linux\${PYTHONPATH:+:\$PYTHONPATH}" exec /usr/bin/env python3 -m apexlinux "\$@"
EOF
chmod +x "$HOME/.local/bin/apex"
cat > "$data_home/applications/apex.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=APEX
Comment=F1 widgets: pick your driver and add widgets to your desktop
Exec=$HOME/.local/bin/apex
Icon=$root/windows/APEX/Assets/Square150x150Logo.png
Categories=Utility;
EOF
cat > "$config_home/autostart/apex-desktop.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=APEX desktop widgets
Exec=$HOME/.local/bin/apex --desktop
NoDisplay=true
EOF

# 3. Desktop widgets now (a no-op if they're already running).
nohup "$HOME/.local/bin/apex" --desktop >/dev/null 2>&1 &

for _ in $(seq 20); do
    status=$(curl -fsS --max-time 2 http://localhost:8077/api/season/current 2>/dev/null) && break
    sleep 1
done
if [ -n "${status:-}" ]; then
    echo "APEX installed. Data server: $(python3 -c 'import json,sys; s=json.load(sys.stdin); print("season %s, next round %s" % (s["year"], s["next_round"]))' <<<"$status")."
else
    echo "APEX installed, but the data server isn't answering yet. Check: journalctl --user -u apex-backend, $backend/apex.log" >&2
fi
echo "Desktop widgets are on the right edge of your screen: drag to move, right-click for options."
echo "Open APEX from your app menu (or run: apex) to pick your driver and add widgets."
case "${XDG_CURRENT_DESKTOP:-}" in
    *Hyprland*) echo "Hyprland doesn't run autostart entries: add 'exec-once = $HOME/.local/bin/apex --desktop' to hyprland.conf." ;;
    *sway*) echo "sway doesn't run autostart entries: add 'exec $HOME/.local/bin/apex --desktop' to your sway config." ;;
esac
