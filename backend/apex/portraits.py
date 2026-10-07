"""Driver silhouettes: the official F1 headshot's cut-out, filled with the team colour."""

import io
import re
from functools import lru_cache
from urllib.parse import urlsplit

import httpx
from PIL import Image

from . import cache

DRIVERS_KEY = "openf1:drivers"  # code → {"number", "headshot"}, written by ingest._sync_team_colors
HEADSHOT_HOST = "media.formula1.com"
MAX_BYTES = 5_000_000
RENDITIONS = {206: "2col", 432: "4col", 864: "4col-retina", 1336: "12col"}  # formula1.com image transforms (square PNGs)


def openf1_driver(code: str) -> dict:
    return (cache.get_json(DRIVERS_KEY) or {}).get(code, {})


@lru_cache(maxsize=32)
def _download(url: str) -> bytes:
    # No redirects: a redirect could send this server anywhere. F1's CDN answers directly.
    r = httpx.get(url, timeout=15, follow_redirects=False)
    r.raise_for_status()
    if len(r.content) > MAX_BYTES:
        raise ValueError("headshot too large")
    return r.content


def _is_f1_media(url: str) -> bool:
    """The URL comes from an external feed: only plain https on F1's media host may be fetched."""
    try:
        u = urlsplit(url)
        return u.scheme == "https" and u.hostname == HEADSHOT_HOST and u.port is None and not u.username and not u.password
    except ValueError:
        return False


@lru_cache(maxsize=64)
def _render(url: str, color: str) -> bytes:
    photo = Image.open(io.BytesIO(_download(url))).convert("RGBA")
    fill = Image.new("RGBA", photo.size, tuple(int(color[i:i + 2], 16) for i in (0, 2, 4)) + (255,))
    fill.putalpha(photo.getchannel("A"))
    out = io.BytesIO()
    fill.save(out, "PNG", optimize=True)
    return out.getvalue()


def silhouette(code: str, color: str, size: int) -> bytes | None:
    """PNG of the driver's silhouette in `color` (RRGGBB), or None when there is no official headshot."""
    url = openf1_driver(code).get("headshot") or ""
    if not _is_f1_media(url):
        return None
    return _render(re.sub(r"\.transform/[^/]+/", f".transform/{RENDITIONS[size]}/", url), color)
