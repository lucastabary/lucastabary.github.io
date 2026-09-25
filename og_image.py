"""Open Graph images: the 1200x630 preview shown when a page is shared.

One PNG per page, drawn with Pillow in the site's own typefaces (the OFL fonts
in ``fonts/``): a small eyebrow, the title, a line of summary, the author, and
the graph motif from the home page. Social networks ignore SVG previews, hence
a raster image.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTS_DIR = Path(__file__).resolve().parent / "fonts"
SANS = FONTS_DIR / "Inter.ttf"
SERIF = FONTS_DIR / "SourceSerif4.ttf"

W, H = 1200, 630
PAD = 80

# The light theme of assets/style.css.
BG = (253, 253, 251)
TEXT = (27, 27, 25)
MUTED = (109, 109, 103)
FAINT = (147, 147, 140)
BORDER = (230, 229, 224)
ACCENT = (39, 72, 156)

# Same nodes and edges as the graph beside the name on the home page.
NODES = [(30, 40, 5), (85, 25, 6.5), (60, 95, 7), (140, 50, 6), (115, 110, 8),
         (178, 92, 5), (95, 155, 4.5), (160, 150, 5.5), (20, 130, 4)]
HUBS = {2, 4}
EDGES = [(0, 1), (0, 2), (1, 2), (1, 3), (2, 4), (3, 4), (3, 5), (4, 5),
         (4, 6), (5, 7), (6, 7), (2, 8)]


@lru_cache(maxsize=None)
def font(path: Path, size: int, weight: int) -> ImageFont.FreeTypeFont:
    """A variable font instance at a given size and weight (optical size follows size)."""
    face = ImageFont.truetype(str(path), size)
    axes = face.get_variation_axes()
    values = []
    for axis in axes:
        name = axis["name"].decode() if isinstance(axis["name"], bytes) else axis["name"]
        if name.lower().startswith("weight"):
            value = weight
        elif name.lower().startswith("optical"):
            value = size * 0.75           # px to pt, roughly
        else:
            value = axis["default"]
        values.append(max(axis["minimum"], min(axis["maximum"], value)))
    face.set_variation_by_axes(values)
    return face


def wrap(text: str, face: ImageFont.FreeTypeFont, width: int, max_lines: int) -> list[str]:
    """Greedy word wrap; the last line ends with an ellipsis if text is left over."""
    words, lines, line = text.split(), [], ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if face.getlength(candidate) <= width:
            line = candidate
            continue
        if line:
            lines.append(line)
        line = word
        if len(lines) == max_lines:
            break
    else:
        if line:
            lines.append(line)
        return lines[:max_lines]
    last = lines[max_lines - 1]
    while last and face.getlength(last + "…") > width:
        last = last.rsplit(" ", 1)[0] if " " in last else last[:-1]
    lines[max_lines - 1] = last.rstrip(",.;:—-") + "…"
    return lines[:max_lines]


def tracked(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str,
            face: ImageFont.FreeTypeFont, fill, tracking: float) -> None:
    """Letter-spaced text, which Pillow has no option for."""
    x, y = xy
    for char in text:
        draw.text((x, y), char, font=face, fill=fill)
        x += face.getlength(char) + tracking


def draw_graph(draw: ImageDraw.ImageDraw, origin: tuple[int, int], scale: float) -> None:
    ox, oy = origin
    point = lambda n: (ox + NODES[n][0] * scale, oy + NODES[n][1] * scale)
    for a, b in EDGES:
        draw.line([point(a), point(b)], fill=BORDER, width=max(2, round(1.4 * scale)))
    for i, (_, _, r) in enumerate(NODES):
        x, y = point(i)
        r *= scale
        box = [x - r, y - r, x + r, y + r]
        if i in HUBS:
            draw.ellipse(box, fill=ACCENT)
        else:
            draw.ellipse(box, fill=BG, outline=FAINT, width=max(2, round(1.4 * scale)))


def draw_house(draw: ImageDraw.ImageDraw, x: int, y: int, size: int) -> None:
    """The header's house icon (24-unit viewBox) in a rounded square."""
    draw.rounded_rectangle([x, y, x + size, y + size], radius=size // 4, outline=BORDER, width=2)
    s = size / 24 * 0.62
    ox, oy = x + size * 0.19, y + size * 0.17
    p = lambda px, py: (ox + px * s, oy + py * s)
    width = max(2, round(size / 16))
    draw.line([p(3, 10.5), p(12, 3), p(21, 10.5)], fill=TEXT, width=width, joint="curve")
    draw.line([p(5.5, 8.8), p(5.5, 21), p(10, 21), p(10, 15), p(14, 15), p(14, 21),
               p(18.5, 21), p(18.5, 8.8)], fill=TEXT, width=width, joint="curve")


def render(out: Path, *, title: str, eyebrow: str = "", summary: str = "",
           footer: str = "", site: str = "") -> None:
    """Draw one preview image to ``out``."""
    image = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(image)

    # Accent rule down the left edge, and the graph in the lower right corner.
    draw.rectangle([0, 0, 10, H], fill=ACCENT)
    draw_graph(draw, (W - 300, H - 270), 1.3)

    # Header: house + site address.
    draw_house(draw, PAD, 64, 44)
    draw.text((PAD + 62, 86), site, font=font(SANS, 24, 500), fill=MUTED, anchor="lm")

    text_width = W - 2 * PAD - 230     # stops short of the graph
    y = 190
    if eyebrow:
        tracked(draw, (PAD, y), eyebrow.upper(), font(SANS, 22, 600), ACCENT, 2.4)
        y += 50

    # The title shrinks until it fits in three lines.
    for size in (68, 60, 52, 46):
        face = font(SANS, size, 600)
        lines = wrap(title or "Untitled", face, text_width, 3)
        if not lines[-1].endswith("…"):
            break
    for line in lines:
        draw.text((PAD, y), line, font=face, fill=TEXT)
        y += round(size * 1.18)

    if summary and len(lines) < 3:
        y += 18
        body = font(SERIF, 30, 400)
        for line in wrap(summary, body, text_width - 60, 3 - len(lines) + 1):
            draw.text((PAD, y), line, font=body, fill=MUTED)
            y += 42

    if footer:
        draw.text((PAD, H - 72), footer, font=font(SANS, 24, 500), fill=FAINT, anchor="ls")

    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out, "PNG", optimize=True)
