"""apex --desktop: hosts the desktop widgets, one frameless WebKit window per widget kept on the desktop layer
(port of windows/APEX/DesktopHost.cs).

Wayland compositors with layer-shell (Hyprland, sway, KDE): each widget is a bottom-layer surface placed by margins,
so tiling never touches it. X11: an undecorated window kept below, moved by the window manager. Other Wayland
sessions (GNOME): a plain undecorated window; the compositor decides where it goes and what sits above it."""
import fcntl
import os
import tempfile
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import IO
from urllib.parse import urlencode

import gi
from gi.repository import Gdk, Gio, GLib, Gtk

from . import config
from .config import DesktopWidget
from .host import HostedPage, log_error, spawn

try:
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import GtkLayerShell
except (ValueError, ImportError):
    GtkLayerShell = None

PX = {"s": (170, 170), "m": (364, 170), "l": (364, 382)}  # logical px, same as Windows at 100%
INSET = 24
STEP = 170 + 16  # unplaced widgets stack down the right edge


def primary_monitor() -> Gdk.Monitor:
    display = Gdk.Display.get_default()
    return display.get_primary_monitor() or display.get_monitor(0)


class WidgetWindow(Gtk.Window):
    def __init__(self, item: DesktopWidget, stack: int, on_command: Callable[["WidgetWindow", str], None]) -> None:
        super().__init__(title="APEX widget")
        self.item = item
        self.on_command = on_command
        self.layer = GtkLayerShell is not None and GtkLayerShell.is_supported()
        self.grab: tuple[float, float] | None = None  # layer-shell drag: pointer position inside the widget
        self.moving = False  # X11 drag: the window manager is moving us
        self.settle = 0
        self.pos = (0, 0)

        self.page = HostedPage(self.on_message, "#15151E", retry_seconds=5)
        self.add(self.page.view)
        self.set_decorated(False)
        self.set_resizable(False)
        if self.layer:
            GtkLayerShell.init_for_window(self)
            GtkLayerShell.set_layer(self, GtkLayerShell.Layer.BOTTOM)
            GtkLayerShell.set_namespace(self, "apex-widget")  # for compositor rules (blur, animations)
            GtkLayerShell.set_monitor(self, primary_monitor())
            GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.TOP, True)
            GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.LEFT, True)
            GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.NONE)
            self.page.view.connect("motion-notify-event", self.on_motion)
            self.page.view.connect("button-release-event", self.on_release)
        else:
            self.set_skip_taskbar_hint(True)  # not in the taskbar or Alt+Tab: it lives on the desktop
            self.set_skip_pager_hint(True)
            self.set_keep_below(True)
            self.set_accept_focus(False)
            self.stick()
            self.connect("configure-event", self.on_configure)
        self.place(stack)
        self.show_all()
        self.navigate()

    def place(self, stack: int) -> None:
        w, h = PX[self.item.Size]
        x, y = self.item.X, self.item.Y
        if x < 0 or y < 0:
            area = primary_monitor().get_workarea()
            # Layer margins are relative to the monitor; X11 positions are global.
            left, top = (0, 0) if self.layer else (area.x, area.y)
            x = left + area.width - w - INSET
            y = top + INSET + stack * STEP
        self.pos = (x, y)
        self.set_size_request(w, h)
        self.resize(w, h)
        self.move_to(x, y)

    def move_to(self, x: int, y: int) -> None:
        self.pos = (x, y)
        if self.layer:
            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.LEFT, x)
            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.TOP, y)
        else:
            self.move(x, y)

    def apply(self, item: DesktopWidget) -> None:
        """New size or kind; keep the widget where it is."""
        self.item = replace(item, X=self.pos[0], Y=self.pos[1])
        self.place(0)
        self.navigate()

    def navigate(self) -> None:
        defaults = config.load_defaults()
        query = {"w": self.item.Kind, "s": self.item.Size, "density": defaults.Density}
        if defaults.Driver:
            query["driver"] = defaults.Driver
        self.page.load(f"{config.BASE_URL}/desktop.html?{urlencode(query)}")

    def on_message(self, message: object) -> None:
        match message:
            case "drag":
                self.start_drag()
            case "size:s" | "size:m" | "size:l":
                self.apply(replace(self.item, Size=message[5:]))
                self.on_command(self, "resized")
            case "remove" | "settings":
                self.on_command(self, message)

    def start_drag(self) -> None:
        pointer = self.get_display().get_default_seat().get_pointer()
        _, px, py, mask = self.get_window().get_device_position(pointer)
        # The page's message can arrive after the button is already up; starting a move then would follow the
        # cursor until the next click.
        if not mask & Gdk.ModifierType.BUTTON1_MASK:
            return
        if self.layer:
            self.grab = (px, py)
        else:
            _, rx, ry = pointer.get_position()
            self.moving = True
            self.begin_move_drag(1, rx, ry, Gtk.get_current_event_time())

    def on_motion(self, _view: Gtk.Widget, event: Gdk.EventMotion) -> bool:
        if self.grab:  # coordinates are relative to the widget, so the offset from the grab point is the move
            self.move_to(self.pos[0] + round(event.x - self.grab[0]), self.pos[1] + round(event.y - self.grab[1]))
        return False  # the page still gets the event

    def on_release(self, _view: Gtk.Widget, _event: Gdk.EventButton) -> bool:
        if self.grab:
            self.grab = None
            self.moved()
        return False

    def on_configure(self, _window: Gtk.Window, _event: Gdk.EventConfigure) -> bool:
        if self.moving:  # the window manager reports each step; save once it has settled
            if self.settle:
                GLib.source_remove(self.settle)
            self.settle = GLib.timeout_add(500, self.on_settled)
        return False

    def on_settled(self) -> bool:
        self.settle = 0
        self.moving = False
        self.pos = self.get_position()
        self.moved()
        return False

    def moved(self) -> None:
        self.item = replace(self.item, X=self.pos[0], Y=self.pos[1])
        self.on_command(self, "moved")


class DesktopHost:
    def __init__(self) -> None:
        self.windows: dict[str, WidgetWindow] = {}
        self.changed: set[str] = set()
        self.debounce = 0
        # First run: start with Race Mode and the favourite driver, so the desktop isn't empty.
        if config.load_desktop() is None:
            config.save_desktop([DesktopWidget("race", "race", "m"), DesktopWidget("fav", "fav", "m")])
        self.sync()
        # desktop.json: widgets added/moved/removed. defaults.json: favourite driver or density changed in the app.
        self.monitor = Gio.File.new_for_path(str(config.data_dir())).monitor_directory(
            Gio.FileMonitorFlags.WATCH_MOVES, None)
        self.monitor.connect("changed", self.on_file_changed)

    def on_file_changed(self, _monitor: Gio.FileMonitor, file: Gio.File, other: Gio.File | None,
                        _event: Gio.FileMonitorEvent) -> None:
        # Settings are swapped in by rename, so the name can be on either side of the event.
        for f in (file, other):
            if f is not None and f.get_basename() in ("desktop.json", "defaults.json"):
                self.changed.add(f.get_basename())
        if self.changed and not self.debounce:
            self.debounce = GLib.timeout_add(200, self.on_settled)

    def on_settled(self) -> bool:
        self.debounce = 0
        changed, self.changed = self.changed, set()
        if "desktop.json" in changed:
            self.sync()
        if "defaults.json" in changed:
            for w in self.windows.values():
                w.navigate()
        return False

    def sync(self) -> None:
        """Make the open windows match desktop.json (adds from the app, size changes, removals)."""
        try:
            items = config.load_desktop() or []
        except OSError as e:
            log_error(f"(handled) {e!r}")  # keep the widgets as they are; the next change retries
            return
        ids = {i.Id for i in items}
        for wid in [wid for wid in self.windows if wid not in ids]:
            self.windows.pop(wid).destroy()
        stack = 0
        for item in items:
            w = self.windows.get(item.Id)
            if w is None:
                self.windows[item.Id] = WidgetWindow(item, stack, self.on_command)
                stack += 1
            elif (w.item.Size, w.item.Kind) != (item.Size, item.Kind):
                w.apply(item)

    def on_command(self, w: WidgetWindow, cmd: str) -> None:
        try:
            if cmd == "settings":
                spawn()
            elif cmd == "remove":
                config.remove_widget(w.item.Id)
            else:  # moved or resized: persist
                config.update_widget(w.item)
        except OSError as e:
            log_error(f"(handled) {e!r}")


def single_instance() -> IO[str] | None:
    """One host per user session; later launches just exit (the host watches desktop.json). Keep the file open."""
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir())
    lock = open(runtime / f"apex-desktop-{os.getuid()}.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        return None
    return lock


def run() -> None:
    lock = single_instance()
    if lock is None:
        return
    config.data_dir().mkdir(parents=True, exist_ok=True)
    _host = DesktopHost()
    Gtk.main()  # keeps running with zero widgets
