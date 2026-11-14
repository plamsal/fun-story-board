"""Draws the shareable card: a 1200x630 picture with the story's closing
line and title. It is also the picture shown when the circle link is posted
on Facebook or LinkedIn.

The card never shows friends' names or words, only the title and closing line.

    make_card(closing, title) -> PNG bytes
"""

from functools import lru_cache
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTS = Path(__file__).parent / "static" / "fonts"
WIDTH, HEIGHT = 1200, 630
MARGIN = 44

INK = "#2b2433"
MUTED = "#776f80"
AMBER = "#a2610c"
PAPER = "#fffaf2"
# Sunrise colours for the four corners: top-left, top-right, bottom-left, bottom-right.
CORNERS = ["#ffdcae", "#ffcfc4", "#fbdde8", "#e2d8fa"]

DEFAULT_CLOSING = "A few words each. One story a day."
TAGLINE = "Story Board  ·  a few words from each friend, one story a day"


def _font(size: int, italic: bool = False, weight: int = 400) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(str(FONTS / ("Lora-Italic.ttf" if italic else "Lora.ttf")), size)
    font.set_variation_by_axes([weight])
    return font


def _wrap(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if line and font.getlength(trial) > max_width:
            lines.append(line)
            line = word
        else:
            line = trial
    return lines + [line] if line else lines


def _fit(text: str, max_width: int, max_height: int, sizes: range, **font_args):
    """The largest font size at which the wrapped text fits in max_height."""
    for size in sizes:
        font = _font(size, **font_args)
        lines = _wrap(text, font, max_width)
        if len(lines) * int(size * 1.3) <= max_height:
            break
    return font, lines


def _centered(draw, y: int, text: str, font, fill: str, spacing: float = 0) -> None:
    """Draw one centred line. `spacing` adds space between letters."""
    if not spacing:
        draw.text((WIDTH / 2, y), text, font=font, fill=fill, anchor="ma")
        return
    widths = [font.getlength(ch) + spacing for ch in text]
    x = (WIDTH - sum(widths) + spacing) / 2
    for ch, width in zip(text, widths):
        draw.text((x, y), ch, font=font, fill=fill)
        x += width


def _diamond(draw, cx: float, cy: float, r: int, fill: str) -> None:
    draw.polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)], fill=fill)


@lru_cache(maxsize=64)
def make_card(closing: str = "", title: str = "") -> bytes:
    closing = closing or DEFAULT_CLOSING

    # Background: a soft four-corner gradient, then a paper panel on top.
    corners = Image.new("RGB", (2, 2))
    corners.putdata([tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) for c in CORNERS])
    image = corners.resize((WIDTH, HEIGHT), Image.Resampling.BILINEAR)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((MARGIN, MARGIN, WIDTH - MARGIN, HEIGHT - MARGIN), radius=40, fill=PAPER)

    # The middle block (label, quote, title) is centred in the space above the tagline.
    title_font = _font(30)
    title_text = f"from \u201c{title}\u201d" if title else ""
    if title_text and title_font.getlength(title_text) > 940:
        title_text = _wrap(title_text, title_font, 900)[0] + "\u2026\u201d"

    label_height, title_height = 80, (104 if title_text else 0)
    space = HEIGHT - 2 * MARGIN - 100  # panel height minus the tagline strip
    quote_font, quote_lines = _fit(f"\u201c{closing}\u201d", 940,
                                   space - label_height - title_height - 50,
                                   range(68, 26, -4), italic=True)
    line_height = int(quote_font.size * 1.3)
    block = label_height + len(quote_lines) * line_height + title_height
    y = MARGIN + (space - block) // 2 + 14

    _centered(draw, y, "CARRY THIS INTO YOUR DAY", _font(24, weight=600), AMBER, spacing=5)
    y += 34 + 46
    for line in quote_lines:
        _centered(draw, y, line, quote_font, INK)
        y += line_height
    if title_text:
        _diamond(draw, WIDTH / 2, y + 30, 8, AMBER)
        y += 64
        _centered(draw, y, title_text, title_font, MUTED)

    _centered(draw, HEIGHT - MARGIN - 62, TAGLINE, _font(24), MUTED)

    out = BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()
