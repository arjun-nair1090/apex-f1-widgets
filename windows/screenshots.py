"""Widget picker previews (APEX/Assets/Screenshots/<Kind>.png), made from the real widgets the way Windows asks for
them: the medium size, 300 x 304, transparent rounded corners. Re-run after changing how the widgets look:

    APEX.exe -DumpImages <dir> max_verstappen
    backend\\.venv\\Scripts\\python windows\\screenshots.py <dir>
"""
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

# Kind (as -DumpImages names its files) -> DisplayName in Package.appxmanifest, shown in the header like the board does.
NAMES = {
    "Race": "APEX", "Next": "Next session", "Countdown": "Countdown", "Timing": "Live timing", "Driver": "Driver",
    "Favourite": "Favourite driver", "Wdc": "Drivers' championship", "Wcc": "Constructors' championship",
    "Weekend": "Race weekend", "Circuit": "Circuit",
}
W, H, RADIUS = 300, 304, 8
SCALE = 2  # -DumpImages renders at 2x; draw at 2x too and scale down once at the end

assets = Path(__file__).parent / "APEX" / "Assets"
out = assets / "Screenshots"
out.mkdir(exist_ok=True)
icon = Image.open(assets / "WidgetIcon.png").convert("RGBA").resize((16 * SCALE, 16 * SCALE), Image.LANCZOS)
font = ImageFont.truetype("seguisb.ttf", 12 * SCALE)  # Segoe UI Semibold, the board's header type

for kind, name in NAMES.items():
    img = Image.open(Path(sys.argv[1]) / f"{kind}-medium.png").convert("RGBA").resize((W * SCALE, H * SCALE), Image.LANCZOS)
    # The top 48 px are left empty for the header the board draws: the app icon and the widget's name.
    img.alpha_composite(icon, (16 * SCALE, 16 * SCALE))
    ImageDraw.Draw(img).text((40 * SCALE, 24 * SCALE), name, font=font, fill=(255, 255, 255), anchor="lm")
    corners = Image.new("L", img.size, 0)
    ImageDraw.Draw(corners).rounded_rectangle((0, 0, img.width - 1, img.height - 1), RADIUS * SCALE, fill=255)
    img.putalpha(ImageChops.multiply(img.getchannel("A"), corners))
    img.resize((W, H), Image.LANCZOS).save(out / f"{kind}.png", optimize=True)
    print(out / f"{kind}.png")
