"""Driver silhouettes: the official F1 headshot's cut-out, filled with the team colour and glowing."""

import colorsys
import io
import re
from functools import lru_cache
from urllib.parse import urlsplit

import httpx
from PIL import Image, ImageChops, ImageFilter

from . import cache

DRIVERS_KEY = "openf1:drivers"  # code → {"number", "headshot"}, written by ingest._sync_team_colors
HEADSHOT_HOST = "media.formula1.com"
MAX_BYTES = 5_000_000
RENDITIONS = {206: "2col", 432: "4col", 864: "4col-retina", 1336: "12col"}  # formula1.com image transforms (square PNGs)
DEEP_FILL = {"ferrari", "red_bull"}  # teams filled with their own colour, darkened, rather than the lifted one


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


def _neon(rgb: tuple[int, ...]) -> tuple[int, ...]:
    """The team colour lifted to glow brightness, so dark teams still light up a dark widget. Greys stay grey."""
    h, lum, s = colorsys.rgb_to_hls(*(c / 255 for c in rgb))
    return tuple(round(c * 255) for c in colorsys.hls_to_rgb(h, max(lum, 0.62), max(s, 0.85) if s > 0.08 else s))


def _mix(a: tuple[int, ...], b: tuple[int, ...], t: float) -> tuple[int, ...]:
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


@lru_cache(maxsize=64)
def _render(url: str, color: str, team_id: str | None = None) -> bytes:
    photo = Image.open(io.BytesIO(_download(url))).convert("RGBA")
    rgb = tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))
    glow = _neon(rgb)
    alpha = photo.getchannel("A")
    w, h = photo.size
    pad = max(6, w // 16)

    # The silhouette: one solid fill in the team colour, lifted so it stands out on a dark widget (or deepened for
    # DEEP_FILL teams; their glow stays bright).
    cutout = Image.new("RGBA", photo.size, _mix(rgb, (0, 0, 0), 0.15) if team_id in DEEP_FILL else glow)
    cutout.putalpha(alpha)

    # Rim light: a bright line just inside the outline.
    k = max(3, (w // 140) | 1)
    rim = Image.new("RGBA", photo.size, _mix(glow, (255, 255, 255), 0.7))
    rim.putalpha(ImageChops.subtract(alpha, alpha.filter(ImageFilter.MinFilter(k))).filter(ImageFilter.GaussianBlur(w / 400)))
    cutout.alpha_composite(rim)

    # Outer glow, a tight halo plus a wide bloom, on a canvas padded at the sides and top (the shoulders still run
    # off the bottom edge).
    shape = Image.new("L", (w + 2 * pad, h + pad), 0)
    shape.paste(alpha, (pad, pad))
    tight = shape.filter(ImageFilter.GaussianBlur(pad / 6)).point(lambda a: min(255, int(a * 1.8)))
    bloom = shape.filter(ImageFilter.GaussianBlur(pad / 2)).point(lambda a: min(255, int(a * 1.5)))
    canvas = Image.new("RGBA", shape.size, glow)
    canvas.putalpha(ImageChops.lighter(tight, bloom))
    canvas.alpha_composite(cutout, (pad, pad))

    out = io.BytesIO()
    canvas.save(out, "PNG", optimize=True)
    return out.getvalue()


def silhouette(code: str, color: str, size: int, team_id: str | None = None) -> bytes | None:
    """PNG of the driver's glowing silhouette in `color` (RRGGBB), or None when there is no official headshot."""
    url = openf1_driver(code).get("headshot") or ""
    if not _is_f1_media(url):
        return None
    return _render(re.sub(r"\.transform/[^/]+/", f".transform/{RENDITIONS[size]}/", url), color, team_id)
