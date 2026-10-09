"""Driver portraits: the official F1 headshot in full colour, with the driver's helmet glowing in front of it."""

import colorsys
import io
import re
import unicodedata
from functools import lru_cache
from urllib.parse import urlsplit

import httpx
from PIL import Image, ImageChops, ImageEnhance, ImageFilter

from . import cache

DRIVERS_KEY = "openf1:drivers"  # code → {"number", "headshot"}, written by ingest._sync_team_colors
HEADSHOT_HOST = "media.formula1.com"
MAX_BYTES = 5_000_000
RENDITIONS = {206: "2col", 432: "4col", 864: "4col-retina", 1336: "12col"}  # formula1.com image transforms (square PNGs)
# ponytail: 2024 is the last helmet set F1 published, so drivers who've changed teams wear their old helmet and rookies
# have none (they get the face alone). Point this at a newer set, or a folder of our own, when one exists.
HELMETS = "https://media.formula1.com/content/dam/fom-website/manual/Helmets2024/{}.png"


def openf1_driver(code: str) -> dict:
    return (cache.get_json(DRIVERS_KEY) or {}).get(code, {})


def helmet_url(last_name: str) -> str:
    """F1 names helmet renders by the plain surname: Hülkenberg → hulkenberg."""
    plain = unicodedata.normalize("NFKD", last_name).encode("ascii", "ignore").decode()
    return HELMETS.format(re.sub(r"[^a-z]", "", plain.lower()))


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


def _tinted(alpha: Image.Image, rgb: tuple[int, ...], k: float = 1.0) -> Image.Image:
    layer = Image.new("RGBA", alpha.size, rgb)
    layer.putalpha(alpha.point(lambda a: min(255, int(a * k))))
    return layer


def _helmet(url: str, glow: tuple[int, ...]) -> Image.Image | None:
    """The helmet tilted nose-down, lit from above, with a team-colour bloom and a white-hot rim. None if F1 has none."""
    try:
        im = Image.open(io.BytesIO(_download(url))).convert("RGBA")
    except (httpx.HTTPError, ValueError, OSError):
        return None
    im = im.crop(im.getchannel("A").getbbox()).rotate(-4, Image.BICUBIC, expand=True)
    im = ImageEnhance.Contrast(im).enhance(1.25)
    # Low-key light: the lower half falls into shadow.
    shade = Image.linear_gradient("L").resize(im.size).point(lambda v: 255 - int(max(0, v - 110) * 0.9))
    lit = Image.merge("RGB", [ImageChops.multiply(c, shade) for c in im.convert("RGB").split()])
    lit.putalpha(im.getchannel("A"))
    # Glow at full resolution (it's resized down later), on a margin wide enough for the bloom.
    m = im.width // 12
    alpha = Image.new("L", (im.width + 2 * m, im.height + 2 * m), 0)
    alpha.paste(im.getchannel("A"), (m, m))
    out = _tinted(alpha.filter(ImageFilter.GaussianBlur(im.width / 46)), glow, 1.6)
    out.alpha_composite(lit, (m, m))
    rim = ImageChops.subtract(alpha, alpha.filter(ImageFilter.MinFilter(5))).filter(ImageFilter.GaussianBlur(0.8))
    out.alpha_composite(_tinted(rim, _mix(glow, (255, 255, 255), 0.5), 0.8))
    return out


@lru_cache(maxsize=64)
def _render(url: str, color: str, helmet: str) -> bytes:
    face = Image.open(io.BytesIO(_download(url))).convert("RGBA")
    face = ImageEnhance.Brightness(face).enhance(0.75)
    w = face.width
    art = _helmet(helmet, _neon(tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))))
    if art is None:
        canvas = face
    else:
        # Face-off: the face on the left fading out to the right, the helmet in front of the shoulder, bottom right.
        fade = Image.linear_gradient("L").rotate(90, expand=True).resize(face.size).point(lambda v: 255 - max(0, v - 60))
        face.putalpha(ImageChops.multiply(face.getchannel("A"), fade))
        canvas = Image.new("RGBA", (round(w * 1.25), w), (0, 0, 0, 0))
        canvas.alpha_composite(face)
        s = 0.6 * w / (art.width * 12 / 14)  # the helmet itself (without its glow margin) spans 0.6 of the face
        art = art.resize((round(art.width * s), round(art.height * s)), Image.LANCZOS)
        m = round(art.width / 14)  # the glow margin, scaled
        canvas.alpha_composite(art, (canvas.width - art.width + m - w // 50, w - art.height + m - w // 20))
    out = io.BytesIO()
    canvas.save(out, "PNG", optimize=True)
    return out.getvalue()


def portrait(code: str, last_name: str, color: str, size: int) -> bytes | None:
    """PNG of the driver's face with their helmet glowing in `color` (RRGGBB), or None when there is no official
    headshot. Drivers without a helmet render get the face alone."""
    url = openf1_driver(code).get("headshot") or ""
    if not _is_f1_media(url):
        return None
    return _render(re.sub(r"\.transform/[^/]+/", f".transform/{RENDITIONS[size]}/", url), color, helmet_url(last_name))
