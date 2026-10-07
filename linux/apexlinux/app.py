"""The APEX app: settings and the widget gallery. The screen is app.html from the data server; this window is the
bridge that owns the settings files (port of windows/APEX/App.cs)."""
from dataclasses import replace

from gi.repository import Gdk, Gtk

from . import config
from .host import HostedPage, log_error, spawn

WAITING = ("<body style='background:#0E0E14;color:#fff;font:600 16px sans-serif;display:grid;place-items:center;"
           "height:90vh'>Starting the APEX data server…</body>")


class SettingsWindow(Gtk.Window):
    def __init__(self) -> None:
        super().__init__(title="APEX")
        self.page = HostedPage(self.on_message, "#0E0E14", retry_seconds=4, waiting_html=WAITING)
        self.add(self.page.view)
        display = Gdk.Display.get_default()
        area = (display.get_primary_monitor() or display.get_monitor(0)).get_workarea()
        self.set_default_size(min(1280, area.width * 9 // 10), min(1000, area.height * 9 // 10))
        self.connect("destroy", Gtk.main_quit)
        self.show_all()
        self.page.load(f"{config.BASE_URL}/app.html")

    def on_message(self, message: object) -> None:
        """Commands from app.html. Every reply carries the full state, so the page never drifts from the files."""
        m = message if isinstance(message, dict) else {}
        done = error = None
        try:
            defaults = config.load_defaults()
            match m.get("cmd"):
                case "setDriver":
                    driver = m.get("id")
                    config.save_defaults(replace(defaults, Driver=driver if isinstance(driver, str) and driver else None))
                    done = "Driver updated"
                case "setDensity" if m.get("value") in config.DENSITIES:
                    config.save_defaults(replace(defaults, Density=m["value"]))
                case "addDesktop" if m.get("size") in config.SIZES and isinstance(m.get("kind"), str):
                    config.add_widget(m["kind"], m["size"])
                    spawn("--desktop")  # single instance: exits at once if the host is already running
                    done = "Added to your desktop"
                case "removeDesktop" if isinstance(m.get("id"), str):
                    config.remove_widget(m["id"])
                    done = "Removed from your desktop"
        except OSError as e:  # a full disk, a read-only home: say so on screen, never close the app
            error = "Couldn't save just now. Try again."
            log_error(f"(handled) {e!r}")
        self.send_state(done, error)

    def send_state(self, done: str | None, error: str | None) -> None:
        defaults = config.load_defaults()
        try:
            desktop = config.load_desktop() or []
        except OSError:
            desktop = []
        self.page.send({
            "type": "state", "driver": defaults.Driver, "density": defaults.Density, "done": done, "error": error,
            "desktop": [{"id": w.Id, "kind": w.Kind, "size": w.Size} for w in desktop],
        })


def run() -> None:
    Gtk.Settings.get_default().set_property("gtk-application-prefer-dark-theme", True)  # carbon-like title bar
    SettingsWindow()
    Gtk.main()
