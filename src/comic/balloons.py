#!/usr/bin/env python3
"""
src/comic/balloons.py — Professional comic balloon renderer.

Implements the balloon conventions documented in docs/COMIC_PRODUCTION.md
and Eric's hard rules (see data/STAGE2_REVISED_PLAN.md):

  Normal speech   — rounded rectangle, smooth tapered tail
  Radio / comm    — double outline, NO tail, inline 'Speaker via Comms:' prefix
                    (Star Trek combadge/viewscreen/intercom). The inline prefix
                    in red conveys the signal — not a zig-zag tail.
  Shout           — jagged burst outline, larger bold text
  Whisper         — dashed outline
  Thought         — scalloped cloud edge (legacy; use captions instead)
  Caption         — rectangle, no tail. Yellow standard. Cyan for Captain's Log.

All balloons:
  - pure white fill (#FFFFFF) — NOT cream (cream is for captions)
  - 3px solid black outline (consistent across page)
  - rounded-rect shape (radius ~25-35px) NOT pure ellipse
  - 14-18px internal padding
  - ALL CAPS body text in Komika Text (or Anime Ace as fan-non-commercial fallback)
  - tail terminates ~50-60% toward speaker mouth
  - never has a drop shadow (drop shadow = amateur tell)
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont


# ── Constants from research brief ─────────────────────────────────────────────

BALLOON_FILL    = (255, 255, 255)       # pure white, per Blambot
BALLOON_OUTLINE = (10, 10, 14)          # near-black ink
OUTLINE_W       = 5                     # px at 2K source canvas

CAPTION_YELLOW  = (255, 230, 128)       # #FFE680
CAPTION_CYAN    = (197, 224, 236)       # #C5E0EC — Star Trek log entries
CAPTION_BORDER  = (10, 10, 14)
CAPTION_BORDER_W = 3

TEXT_COLOR      = (15, 15, 22)
SPEAKER_COLOR   = (160, 20, 30)         # used sparingly — inline speaker tags

CORNER_RADIUS   = 36
PADDING_X       = 28
PADDING_Y       = 22
LINE_HEIGHT_MUL = 1.05


# ── Balloon types ─────────────────────────────────────────────────────────────

class BalloonType(Enum):
    NORMAL  = "normal"        # rounded rect, smooth tail
    RADIO   = "radio"         # double outline, no tail, inline 'Speaker via Comms:' prefix (combadge/comm/viewscreen)
    SHOUT   = "shout"         # jagged outline
    WHISPER = "whisper"       # dashed outline
    THOUGHT = "thought"       # scalloped cloud edge
    CAPTION = "caption"       # yellow rectangle, no tail
    LOG     = "log"           # cyan rectangle, italic — Captain's Log


@dataclass
class Balloon:
    """A single balloon to be drawn on the page."""

    text:       str
    speaker:    str = ""
    btype:      BalloonType = BalloonType.NORMAL
    # Where the bubble should be anchored in absolute image coords
    bubble_xy:  Optional[Tuple[float, float]] = None
    # Where to point the tail (absolute coords). None = no tail.
    anchor_xy:  Optional[Tuple[float, float]] = None
    # Off-panel speaker? Then tail anchors to nearest panel edge
    off_panel:  bool = False
    # If True, balloon is butted against panel top (vs. floating)
    anchor_top: bool = True


# ── Font registry ─────────────────────────────────────────────────────────────

class FontRegistry:
    """Cached font loader. Falls back gracefully to system fonts if the
    project fonts directory doesn't exist."""

    def __init__(self, fonts_dir: Optional[Path] = None):
        self.fonts_dir = fonts_dir or (
            Path(__file__).parent.parent.parent / "assets" / "fonts"
        )
        self._cache: dict = {}

    def _try(self, paths, size):
        for p in paths:
            try:
                return ImageFont.truetype(str(p), size)
            except (OSError, IOError):
                continue
        return ImageFont.load_default()

    def dialogue(self, size: int):
        """Body dialogue font (Komika Text Bold → fallback)."""
        key = ("dialogue", size)
        if key in self._cache:
            return self._cache[key]
        paths = [
            self.fonts_dir / "KOMTXTB_.ttf",
            self.fonts_dir / "KOMTXT__.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
        self._cache[key] = self._try(paths, size)
        return self._cache[key]

    def dialogue_italic(self, size: int):
        key = ("dialogue_italic", size)
        if key in self._cache:
            return self._cache[key]
        paths = [
            self.fonts_dir / "KOMTXTI_.ttf",   # regular Italic — preferred (more visible slant)
            self.fonts_dir / "KOMTXTBI.ttf",   # Bold Italic — fallback (heavier, slant less visible)
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf",
        ]
        self._cache[key] = self._try(paths, size)
        return self._cache[key]

    def display(self, size: int):
        """SFX and titles (Bangers)."""
        key = ("display", size)
        if key in self._cache:
            return self._cache[key]
        paths = [
            self.fonts_dir / "Bangers-Regular.ttf",
            self.fonts_dir / "KOMTXTB_.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
        self._cache[key] = self._try(paths, size)
        return self._cache[key]


# ── Text layout helpers ───────────────────────────────────────────────────────

def wrap_text(draw, text: str, font, max_width: int) -> list[str]:
    """Word-wrap text to fit within max_width. Preserves explicit line breaks."""
    paragraphs = text.split("\n")
    lines = []
    for para in paragraphs:
        words = para.split()
        cur = ""
        for w in words:
            trial = f"{cur} {w}".strip()
            if draw.textbbox((0, 0), trial, font=font)[2] <= max_width:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
    return lines


def measure_lines(draw, lines: list[str], font) -> tuple[int, int]:
    """Returns (max_width, total_height) of rendered lines."""
    max_w = 0
    for ln in lines:
        bbox = draw.textbbox((0, 0), ln, font=font)
        max_w = max(max_w, bbox[2] - bbox[0])
    asc, desc = font.getmetrics()
    line_h = int((asc + desc) * LINE_HEIGHT_MUL)
    return max_w, line_h * len(lines)


# ── Shape helpers ─────────────────────────────────────────────────────────────

def _quadratic_bezier(p0, p1, p2, steps=20):
    """Return points along a quadratic Bezier curve."""
    pts = []
    for i in range(steps + 1):
        t = i / steps
        x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t ** 2 * p2[0]
        y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t ** 2 * p2[1]
        pts.append((x, y))
    return pts


# Note: _zigzag_line and _draw_zigzag_tail were removed 2026-06-02.
# Per Eric's hard rules, radio/comm balloons use NO tail. The double
# outline + inline 'Speaker via Comms:' prefix conveys the signal.


def _rounded_rect_outline(draw, rect, radius, outline, width):
    """Wraps Pillow's rounded_rectangle for older versions safely."""
    draw.rounded_rectangle(rect, radius=radius, outline=outline,
                            fill=None, width=width)


# ── Balloon renderers ─────────────────────────────────────────────────────────

def _draw_normal_balloon(img: Image.Image, balloon: Balloon, fonts: FontRegistry,
                          dialogue_size: int = 24):
    """Standard rounded-rect speech balloon with smooth curved tail."""
    draw = ImageDraw.Draw(img, "RGBA")
    font = fonts.dialogue(dialogue_size)

    # Lay out text first to size the balloon
    max_text_w = 700
    lines = wrap_text(draw, balloon.text.upper(), font, max_text_w)
    text_w, text_h = measure_lines(draw, lines, font)

    bw = text_w + PADDING_X * 2
    bh = text_h + PADDING_Y * 2

    cx, cy = balloon.bubble_xy
    rect = (cx - bw // 2, cy - bh // 2, cx + bw // 2, cy + bh // 2)

    # Pure white fill + black rounded-rect outline
    draw.rounded_rectangle(rect, radius=CORNER_RADIUS, fill=BALLOON_FILL)
    _rounded_rect_outline(draw, rect, CORNER_RADIUS, BALLOON_OUTLINE, OUTLINE_W)

    # Tail
    if balloon.anchor_xy:
        _draw_smooth_tail(draw, (cx, cy), bw, bh, balloon.anchor_xy,
                          balloon.off_panel)

    # Text — vertically centered
    asc, desc = font.getmetrics()
    line_h = int((asc + desc) * LINE_HEIGHT_MUL)
    y = cy - text_h // 2
    for ln in lines:
        line_w = draw.textbbox((0, 0), ln, font=font)[2]
        draw.text((cx - line_w // 2, y), ln, font=font, fill=TEXT_COLOR)
        y += line_h


def _draw_radio_balloon(img: Image.Image, balloon: Balloon, fonts: FontRegistry,
                         dialogue_size: int = 24):
    """Double-outline rounded-rect with NO tail.
    Used for combadge / viewscreen / intercom — crucial for Star Trek.

    Three signals convey 'transmitted voice': double outline, italic body
    text, inline `Speaker via Comms:` prefix in red. The reader doesn't
    need a tail. (Italic body added 2026-06-02 per Eric's call.)
    """
    draw = ImageDraw.Draw(img, "RGBA")
    # Two fonts: tag in non-italic (visually distinct from body),
    # body in italic (conveys transmitted voice per Blambot).
    tag_font = fonts.dialogue(dialogue_size)
    body_font = fonts.dialogue_italic(dialogue_size)

    # Compose full text with inline tag
    speaker_prefix = ""
    if balloon.speaker:
        speaker_prefix = f"{balloon.speaker.title()} via Comms: "
    full_text = (speaker_prefix + balloon.text).upper()
    speaker_prefix_upper = speaker_prefix.upper() if speaker_prefix else ""

    # Wrap using body_font (italic) — conservative on width, prevents overflow.
    max_text_w = 700
    lines = wrap_text(draw, full_text, body_font, max_text_w)

    # Measure for balloon sizing. body_font (italic) is the wider font
    # in Komika Text, so using it gives a safely-sized balloon.
    text_w, text_h = measure_lines(draw, lines, body_font)
    bw = text_w + PADDING_X * 2
    bh = text_h + PADDING_Y * 2

    cx, cy = balloon.bubble_xy
    rect = (cx - bw // 2, cy - bh // 2, cx + bw // 2, cy + bh // 2)

    # Outer outline (white fill)
    draw.rounded_rectangle(rect, radius=CORNER_RADIUS, fill=BALLOON_FILL)
    _rounded_rect_outline(draw, rect, CORNER_RADIUS, BALLOON_OUTLINE, OUTLINE_W)
    # Inner outline (offset 5px)
    inner = (rect[0] + 5, rect[1] + 5, rect[2] - 5, rect[3] - 5)
    _rounded_rect_outline(draw, inner, max(4, CORNER_RADIUS - 5),
                          BALLOON_OUTLINE, 1)

    # No tail on radio balloons — the double outline + inline 'via Comms'
    # speaker tag in red + italic body already convey 'this is a transmission'.

    # Text — vertically centered
    asc, desc = body_font.getmetrics()
    line_h = int((asc + desc) * LINE_HEIGHT_MUL)
    y = cy - text_h // 2
    for ln in lines:
        tag_w = 0  # default for non-tag lines
        # Compute actual rendered width: tag (non-italic) + body (italic)
        if speaker_prefix_upper and ln.startswith(speaker_prefix_upper):
            tag_w = draw.textbbox((0, 0), speaker_prefix_upper, font=tag_font)[2]
            body_part = ln[len(speaker_prefix_upper):]
            body_w = draw.textbbox((0, 0), body_part, font=body_font)[2]
            line_w = tag_w + body_w
        else:
            line_w = draw.textbbox((0, 0), ln, font=body_font)[2]

        x = cx - line_w // 2

        # Render: tag in red non-italic, body in black italic
        if speaker_prefix_upper and ln.startswith(speaker_prefix_upper):
            draw.text((x, y), speaker_prefix_upper, font=tag_font, fill=SPEAKER_COLOR)
            body_part = ln[len(speaker_prefix_upper):]
            draw.text((x + tag_w, y), body_part, font=body_font, fill=TEXT_COLOR)
        else:
            draw.text((x, y), ln, font=body_font, fill=TEXT_COLOR)
        y += line_h


def _draw_caption(img: Image.Image, balloon: Balloon, fonts: FontRegistry,
                   dialogue_size: int = 24, italic: bool = False):
    """Rectangle caption box. Yellow for narration, cyan for Captain's Log."""
    draw = ImageDraw.Draw(img, "RGBA")
    font = (fonts.dialogue_italic(dialogue_size) if italic
            else fonts.dialogue(dialogue_size))

    max_text_w = 800
    lines = wrap_text(draw, balloon.text.upper(), font, max_text_w)
    text_w, text_h = measure_lines(draw, lines, font)

    bw = text_w + PADDING_X * 2
    bh = text_h + PADDING_Y * 2

    cx, cy = balloon.bubble_xy
    rect = (cx - bw // 2, cy - bh // 2, cx + bw // 2, cy + bh // 2)

    fill = CAPTION_CYAN if balloon.btype == BalloonType.LOG else CAPTION_YELLOW

    # Thin double-line border, like IDW Star Trek log captions
    draw.rectangle(rect, fill=fill, outline=CAPTION_BORDER, width=CAPTION_BORDER_W)
    if balloon.btype == BalloonType.LOG:
        # Small inner highlight line
        inner = (rect[0] + 4, rect[1] + 4, rect[2] - 4, rect[3] - 4)
        draw.rectangle(inner, outline=CAPTION_BORDER, width=1)

    asc, desc = font.getmetrics()
    line_h = int((asc + desc) * LINE_HEIGHT_MUL)
    y = cy - text_h // 2
    for ln in lines:
        line_w = draw.textbbox((0, 0), ln, font=font)[2]
        draw.text((cx - line_w // 2, y), ln, font=font, fill=TEXT_COLOR)
        y += line_h


# ── Tail drawers ──────────────────────────────────────────────────────────────

def _tail_attach_point(cx, cy, bw, bh, anchor):
    """Return point on balloon edge nearest to anchor, plus perpendicular vector."""
    ax, ay = anchor
    dx, dy = ax - cx, ay - cy
    dist = max(1.0, math.hypot(dx, dy))
    nx, ny = dx / dist, dy / dist
    # Project onto rounded-rect "shell" — approximate via ellipse of the rect
    rx, ry = bw / 2, bh / 2
    # Scale so that point is on ellipse
    scale = 1.0 / math.sqrt((nx / rx) ** 2 + (ny / ry) ** 2)
    edge_x = cx + nx * scale
    edge_y = cy + ny * scale
    perp_x, perp_y = -ny, nx
    return edge_x, edge_y, perp_x, perp_y


def _draw_smooth_tail(draw, balloon_center, bw, bh, anchor, off_panel=False):
    """Smooth tapered tail from balloon to anchor.
    Per Blambot: terminates at ~50-60% toward speaker mouth."""
    cx, cy = balloon_center
    ax, ay = anchor
    edge_x, edge_y, perp_x, perp_y = _tail_attach_point(cx, cy, bw, bh, anchor)

    # Tail tip is at 55% of the way from edge to anchor (don't touch speaker)
    tip_x = edge_x + (ax - edge_x) * 0.55
    tip_y = edge_y + (ay - edge_y) * 0.55

    # Tail base is wider at attachment to bubble, narrows toward tip
    base_half = 14
    bp1 = (edge_x + perp_x * base_half, edge_y + perp_y * base_half)
    bp2 = (edge_x - perp_x * base_half, edge_y - perp_y * base_half)

    # Curve control point — slight jog perpendicular
    mid_x = (edge_x + tip_x) / 2
    mid_y = (edge_y + tip_y) / 2
    jog_amp = 6 if not off_panel else 0
    rng = random.Random(int(ax * 17 + ay * 31) & 0xFFFF)
    jog_sign = 1 if rng.random() > 0.5 else -1
    ctrl_x = mid_x + perp_x * jog_amp * jog_sign
    ctrl_y = mid_y + perp_y * jog_amp * jog_sign

    # Two Bezier curves: bp1 → tip and bp2 → tip
    left  = _quadratic_bezier(bp1, (ctrl_x, ctrl_y), (tip_x, tip_y), steps=14)
    right = _quadratic_bezier(bp2, (ctrl_x, ctrl_y), (tip_x, tip_y), steps=14)

    # Fill tail with white (balloon fill)
    polygon = left + list(reversed(right))
    draw.polygon(polygon, fill=BALLOON_FILL)

    # Outline the two curves
    for curve in (left, right):
        for i in range(len(curve) - 1):
            draw.line([curve[i], curve[i + 1]],
                       fill=BALLOON_OUTLINE, width=OUTLINE_W)

    # Cover the seam where tail meets balloon by re-drawing inner fill
    # (this hides the chord that would otherwise show)
    draw.line([bp1, bp2], fill=BALLOON_FILL, width=OUTLINE_W + 2)


# ── Public API ────────────────────────────────────────────────────────────────

def draw_balloon(img: Image.Image, balloon: Balloon, fonts: FontRegistry,
                 dialogue_size: int = 24):
    """Public entry point — dispatches by balloon type."""
    if balloon.btype in (BalloonType.CAPTION, BalloonType.LOG):
        _draw_caption(img, balloon, fonts, dialogue_size,
                       italic=(balloon.btype == BalloonType.LOG))
    elif balloon.btype == BalloonType.RADIO:
        _draw_radio_balloon(img, balloon, fonts, dialogue_size)
    else:
        # NORMAL + SHOUT + WHISPER + THOUGHT all use normal renderer for now
        # (shape variants can be added incrementally)
        _draw_normal_balloon(img, balloon, fonts, dialogue_size)


__all__ = ["Balloon", "BalloonType", "FontRegistry", "draw_balloon"]
