"""Settings files shared by the APEX app and the desktop host. Same files and JSON shape as the Windows client
(windows/APEX/DesktopHost.cs, Data.cs): desktop.json = [{Id, Kind, Size, X, Y}], defaults.json = {Driver, Density}."""
import json
import os
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

BASE_URL = os.environ.get("APEX_BASE_URL", "http://localhost:8077").rstrip("/")
SIZES = ("s", "m", "l")
DENSITIES = ("minimal", "standard", "detailed")


def data_dir() -> Path:
    """$XDG_DATA_HOME/APEX: where .NET's LocalApplicationData points on Linux too."""
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / "APEX"


@dataclass(frozen=True)
class DesktopWidget:
    """One widget on the desktop. X/Y are logical pixels; -1 = not placed yet."""
    Id: str
    Kind: str
    Size: str
    X: int = -1
    Y: int = -1


@dataclass(frozen=True)
class Defaults:
    Driver: str | None = None
    Density: str = "standard"


def _read(path: Path) -> object | None:
    """None = no file yet. A malformed file reads as {}: present but empty, so it never looks like a first run."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def _write(path: Path, value: object) -> None:
    """Write a temp file and swap it in, so a reader never sees half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(value), encoding="utf-8")
    os.replace(tmp, path)


def _widget(raw: object) -> DesktopWidget | None:
    if not isinstance(raw, dict):
        return None
    wid, kind, size = raw.get("Id"), raw.get("Kind"), raw.get("Size")
    x, y = raw.get("X", -1), raw.get("Y", -1)
    if not (isinstance(wid, str) and wid and isinstance(kind, str) and kind and size in SIZES):
        return None
    if not (isinstance(x, int) and isinstance(y, int)):
        x = y = -1
    return DesktopWidget(wid, kind, size, x, y)


def load_desktop() -> list[DesktopWidget] | None:
    """None = no desktop.json yet (first run). Invalid entries are dropped."""
    raw = _read(data_dir() / "desktop.json")
    if raw is None:
        return None
    if not isinstance(raw, list):
        return []
    return [w for w in map(_widget, raw) if w is not None]


def save_desktop(items: list[DesktopWidget]) -> None:
    _write(data_dir() / "desktop.json", [asdict(w) for w in items])


def add_widget(kind: str, size: str) -> DesktopWidget:
    if size not in SIZES:
        raise ValueError(f"unknown size {size!r}")
    item = DesktopWidget(uuid.uuid4().hex[:8], kind, size)
    save_desktop([*(load_desktop() or []), item])
    return item


def remove_widget(widget_id: str) -> None:
    save_desktop([w for w in load_desktop() or [] if w.Id != widget_id])


def update_widget(item: DesktopWidget) -> None:
    """Persist a moved or resized widget; a widget removed meanwhile stays removed."""
    save_desktop([item if w.Id == item.Id else w for w in load_desktop() or []])


def load_defaults() -> Defaults:
    raw = _read(data_dir() / "defaults.json")
    if not isinstance(raw, dict):
        return Defaults()
    driver = raw.get("Driver")
    density = raw.get("Density")
    return Defaults(driver if isinstance(driver, str) and driver else None,
                    density if density in DENSITIES else "standard")


def save_defaults(defaults: Defaults) -> None:
    if defaults.Density not in DENSITIES:
        raise ValueError(f"unknown density {defaults.Density!r}")
    _write(data_dir() / "defaults.json", asdict(defaults))

