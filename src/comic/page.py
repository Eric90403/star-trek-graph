#!/usr/bin/env python3
"""
src/comic/page.py — Comic page composer.

Lays out N panels on a page using a grid system, applies the post-processing
chain to each panel, places balloons + captions per the layout brief.

Page canvas conventions (from research):
  - 1400 × 2168 (US comic floppy aspect 1:1.547)
  - 50px outer margin
  - 22px inter-panel gutter
  - 3px black panel border
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw

from .balloons import Balloon, BalloonType, FontRegistry, draw_balloon
from .panels   import to_comic_style


# ── Page constants ───────────────────────────────────────────────────────────

PAGE_W, PAGE_H = 1400, 2168
OUTER_MARGIN   = 50
GUTTER         = 22
PANEL_BORDER_W = 3
PANEL_BORDER   = (10, 10, 14)
PAGE_BG        = (255, 255, 255)


# ── Layouts ──────────────────────────────────────────────────────────────────

@dataclass
class PanelRect:
    """A panel's position on the page in absolute pixel coordinates."""
    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def w(self) -> int:
        return self.x1 - self.x0

    @property
    def h(self) -> int:
        return self.y1 - self.y0

    def rel(self, x_pct: float, y_pct: float) -> tuple[int, int]:
        """Convert (x_pct, y_pct) in [0,1] to absolute coords inside panel."""
        return (int(self.x0 + self.w * x_pct),
                int(self.y0 + self.h * y_pct))


def grid_layout(n_panels: int, page_w: int = PAGE_W, page_h: int = PAGE_H,
                outer_margin: int = OUTER_MARGIN, gutter: int = GUTTER,
                title_height: int = 60) -> list[PanelRect]:
    """Return PanelRects for a 'comic standard' grid based on panel count.

    Layouts chosen per Blambot conventions:
      - 1 panel: full-page splash
      - 2 panels: stacked
      - 3 panels: hero + 2 stacked OR 3 horizontal tiers (3 tiers used)
      - 4 panels: 2x2 grid
      - 5 panels: wide top + 2x2 grid
      - 6 panels: 2x3 grid (most common)
      - 9 panels: 3x3 Watchmen grid
    """
    avail_x = page_w - outer_margin * 2
    avail_y = page_h - outer_margin * 2 - title_height
    top = outer_margin + title_height

    def grid(rows, cols):
        cell_w = (avail_x - gutter * (cols - 1)) // cols
        cell_h = (avail_y - gutter * (rows - 1)) // rows
        rects = []
        for r in range(rows):
            for c in range(cols):
                x0 = outer_margin + c * (cell_w + gutter)
                y0 = top + r * (cell_h + gutter)
                rects.append(PanelRect(x0, y0, x0 + cell_w, y0 + cell_h))
        return rects

    if n_panels == 1:
        return [PanelRect(outer_margin, top,
                           outer_margin + avail_x, top + avail_y)]
    elif n_panels == 2:
        return grid(2, 1)
    elif n_panels == 3:
        # Hero panel on top (wide), then two stacked
        h1 = int(avail_y * 0.45)
        h_rest = (avail_y - gutter * 2 - h1) // 2 + 1
        return [
            PanelRect(outer_margin, top,
                       outer_margin + avail_x, top + h1),
            PanelRect(outer_margin, top + h1 + gutter,
                       outer_margin + avail_x,
                       top + h1 + gutter + h_rest),
            PanelRect(outer_margin, top + h1 + gutter + h_rest + gutter,
                       outer_margin + avail_x,
                       top + avail_y),
        ]
    elif n_panels == 4:
        return grid(2, 2)
    elif n_panels == 5:
        # Wide hero top + 2x2 below
        h1 = int(avail_y * 0.30)
        cell_w = (avail_x - gutter) // 2
        cell_h = (avail_y - gutter * 2 - h1) // 2
        rects = [PanelRect(outer_margin, top,
                            outer_margin + avail_x, top + h1)]
        y_under = top + h1 + gutter
        for r in range(2):
            for c in range(2):
                x0 = outer_margin + c * (cell_w + gutter)
                y0 = y_under + r * (cell_h + gutter)
                rects.append(PanelRect(x0, y0, x0 + cell_w, y0 + cell_h))
        return rects
    elif n_panels == 6:
        return grid(3, 2)
    elif n_panels == 9:
        return grid(3, 3)
    else:
        # Generic n: closest grid
        import math
        cols = max(1, int(math.sqrt(n_panels)))
        rows = (n_panels + cols - 1) // cols
        return grid(rows, cols)[:n_panels]


# ── Panel placement ──────────────────────────────────────────────────────────

def place_panel(page: Image.Image, panel_img: Image.Image, rect: PanelRect,
                process: bool = True, seed: Optional[int] = None) -> None:
    """Resize-crop panel_img to fit rect, optionally apply comic post-process,
    then paste with crisp panel border."""
    img = panel_img.convert("RGB")
    src_w, src_h = img.size
    scale = max(rect.w / src_w, rect.h / src_h)
    new = img.resize((int(src_w * scale), int(src_h * scale)),
                     Image.Resampling.LANCZOS)
    nw, nh = new.size
    left = (nw - rect.w) // 2
    top = (nh - rect.h) // 2
    new = new.crop((left, top, left + rect.w, top + rect.h))

    if process:
        new = to_comic_style(new, seed=seed)

    page.paste(new, (rect.x0, rect.y0))
    draw = ImageDraw.Draw(page)
    draw.rectangle((rect.x0, rect.y0, rect.x1 - 1, rect.y1 - 1),
                   outline=PANEL_BORDER, width=PANEL_BORDER_W)


# ── Page header ──────────────────────────────────────────────────────────────

def draw_page_header(page: Image.Image, fonts: FontRegistry,
                      series_title: str, episode_title: str,
                      page_num: int, total_pages: int) -> None:
    draw = ImageDraw.Draw(page)
    title_font = fonts.display(46)
    sub_font   = fonts.dialogue(22)
    draw.text((OUTER_MARGIN, OUTER_MARGIN - 4),
              series_title.upper(),
              font=title_font, fill=(18, 28, 78))
    draw.text((OUTER_MARGIN, OUTER_MARGIN + 44),
              f'"{episode_title}"   ·   Page {page_num} of {total_pages}',
              font=sub_font, fill=(80, 30, 30))


# ── Page footer ──────────────────────────────────────────────────────────────

def draw_page_footer(page: Image.Image, fonts: FontRegistry,
                      text: str = "Generated by star-trek-graph  "
                                  "·  github.com/Eric90403/star-trek-graph") -> None:
    draw = ImageDraw.Draw(page)
    font = fonts.dialogue(13)
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    draw.text((PAGE_W - w - OUTER_MARGIN, PAGE_H - 28),
              text, font=font, fill=(140, 140, 150))


__all__ = ["PanelRect", "grid_layout", "place_panel",
            "draw_page_header", "draw_page_footer",
            "PAGE_W", "PAGE_H", "OUTER_MARGIN", "GUTTER"]
