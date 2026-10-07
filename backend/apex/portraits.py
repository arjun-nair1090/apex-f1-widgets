"""Driver silhouettes: the official F1 headshot's cut-out, filled with the team colour."""

import io
import re
from functools import lru_cache

import httpx
from PIL import Image

from . import cache

DRIVERS_KEY = "openf1:drivers"  # code → {"number", "headshot"}, written by ingest._sync_team_colors
HEADSHOT_HOST = "https://media.formula1.com/"
RENDITIONS = {206: "2col", 432: "4col", 864: "4col-retina", 1336: "12col"}  # formula1.com image transforms (square PNGs)


def openf1_driver(code: str) -> dict:
    return (cache.get_json(DRIVERS_KEY) or {}).get(code, {})


@lru_cache(maxsize=32)
def _download(url: str) -> bytes:
    r = httpx.get(url, timeout=15, follow_redirects=True)
    r.raise_for_status()
    return r.content


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
    # Only fetch from F1's media CDN: the URL comes from an external feed and must not steer our requests.
    if not url.startswith(HEADSHOT_HOST):
        return None
    return _render(re.sub(r"\.transform/[^/]+/", f".transform/{RENDITIONS[size]}/", url), color)
