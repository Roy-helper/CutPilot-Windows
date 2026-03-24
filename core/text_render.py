"""PIL-based text rendering with CJK font support.

Generates styled text card images for video overlays.
"""
from __future__ import annotations

import logging
import platform
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

logger = logging.getLogger(__name__)

# Ordered list of CJK font candidates per platform.
_FONT_CANDIDATES: list[str] = [
    # macOS
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    # Linux
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    # Windows
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
]


def find_cjk_font() -> str | None:
    """Return the first available CJK font path, or None."""
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).is_file():
            logger.debug("Found CJK font: %s", candidate)
            return candidate
    logger.warning("No CJK font found on this system")
    return None


def wrap_text(
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
) -> list[str]:
    """Word-wrap text for Chinese (break on any character).

    Returns a list of lines that each fit within *max_width* pixels.
    Newlines in the input are honoured.
    """
    lines: list[str] = []
    for paragraph in text.split("\n"):
        if not paragraph:
            lines.append("")
            continue
        current = ""
        for char in paragraph:
            test = current + char
            bbox = font.getbbox(test)
            width = bbox[2] - bbox[0]
            if width > max_width and current:
                lines.append(current)
                current = char
            else:
                current = test
        if current:
            lines.append(current)
    return lines


def render_text_card(
    text: str,
    video_width: int,
    font_path: str | None,
    font_size: int,
    *,
    padding_h: int = 30,
    padding_v: int = 20,
    corner_radius: int = 20,
    bg_color: tuple[int, int, int, int] = (0, 0, 0, 200),
    text_color: tuple[int, int, int] = (255, 255, 255),
    shadow_offset: int = 5,
    shadow_blur: int = 6,
) -> Image.Image:
    """Render a styled text card as a PIL RGBA Image.

    The card has a white rounded-rect background, black text, and a soft
    drop shadow.  Returned image width = video_width so FFmpeg overlay can
    centre it trivially.
    """
    font = _load_font(font_path, font_size)
    max_text_width = int(video_width * 0.85) - 2 * padding_h
    lines = wrap_text(text, font, max_text_width)

    line_height = _line_height(font)
    text_block_w = _max_line_width(lines, font)
    text_block_h = line_height * len(lines)

    card_w = text_block_w + 2 * padding_h
    card_h = text_block_h + 2 * padding_v

    # Full-width canvas so the card is already centred horizontally.
    canvas_w = video_width
    canvas_h = card_h + shadow_offset + shadow_blur * 2
    card_x = (canvas_w - card_w) // 2

    # --- shadow layer ---
    shadow = _draw_rounded_rect_shadow(
        canvas_w, canvas_h, card_x, 0, card_w, card_h,
        corner_radius, shadow_offset, shadow_blur,
    )

    # --- card layer ---
    card_layer = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    card_draw = ImageDraw.Draw(card_layer)
    card_draw.rounded_rectangle(
        (card_x, 0, card_x + card_w, card_h),
        radius=corner_radius,
        fill=bg_color,
    )

    # --- text ---
    y = padding_v
    for line in lines:
        bbox = font.getbbox(line)
        lw = bbox[2] - bbox[0]
        x = card_x + (card_w - lw) // 2
        card_draw.text((x, y), line, fill=text_color, font=font)
        y += line_height

    # composite: shadow under card
    result = Image.alpha_composite(shadow, card_layer)
    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_font(font_path: str | None, size: int) -> ImageFont.FreeTypeFont:
    """Load a TrueType font, falling back to PIL default."""
    if font_path:
        try:
            return ImageFont.truetype(font_path, size)
        except (OSError, IOError):
            logger.warning("Failed to load font %s, using default", font_path)
    return ImageFont.load_default(size)


def _line_height(font: ImageFont.FreeTypeFont) -> int:
    """Compute a line height from font metrics."""
    bbox = font.getbbox("Ag中")
    return int((bbox[3] - bbox[1]) * 1.4)


def _max_line_width(lines: list[str], font: ImageFont.FreeTypeFont) -> int:
    """Return the pixel width of the widest line."""
    if not lines:
        return 0
    widths = []
    for line in lines:
        bbox = font.getbbox(line)
        widths.append(bbox[2] - bbox[0])
    return max(widths)


def _draw_rounded_rect_shadow(
    canvas_w: int,
    canvas_h: int,
    x: int,
    y: int,
    w: int,
    h: int,
    radius: int,
    offset: int,
    blur: int,
) -> Image.Image:
    """Draw a soft drop shadow for a rounded rectangle."""
    shadow = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(shadow)
    draw.rounded_rectangle(
        (x + offset, y + offset, x + w + offset, y + h + offset),
        radius=radius,
        fill=(0, 0, 0, 102),  # 40% opacity black
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=blur))
    return shadow
