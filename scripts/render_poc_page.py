#!/usr/bin/env python3
"""
scripts/render_poc_page.py — Render Page 1 of "The Last Voice of Kethani"
using the new comic platform (Tier 1+2 conventions).

Uses pre-generated panel art from data/poc_comic/panels_v2/ to validate
the balloon/typography/post-processing pipeline before wiring up the
full multi-page pipeline.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image

from comic.balloons import Balloon, BalloonType, FontRegistry
from comic.balloons import draw_balloon
from comic.page     import (PAGE_W, PAGE_H, grid_layout, place_panel,
                             draw_page_header, draw_page_footer)


PANEL_DIR = ROOT / "data" / "poc_comic" / "panels_v2"
OUT_PATH  = ROOT / "data" / "poc_comic" / "page1_v3.png"


def main():
    fonts = FontRegistry()

    # Build the page canvas
    page = Image.new("RGB", (PAGE_W, PAGE_H), (255, 255, 255))

    # 6 panels: 1 wide hero + 2 stacked (custom) — but we already have a
    # specific composition in mind. Use a custom layout that matches the
    # POC: 1 wide establisher, 2 side-by-side, then 3 stacked wide.
    from comic.page import PanelRect, GUTTER, OUTER_MARGIN
    title_h = 90
    avail_x = PAGE_W - OUTER_MARGIN * 2
    avail_y = PAGE_H - OUTER_MARGIN * 2 - title_h
    top = OUTER_MARGIN + title_h

    # Hero (wide) - 28% of page
    h1 = int(avail_y * 0.28)
    # Row 2 (split) - 20%
    h2 = int(avail_y * 0.20)
    # Rows 3, 4, 5 - share remaining
    h3 = (avail_y - h1 - h2 - GUTTER * 4) // 3

    half_w = (avail_x - GUTTER) // 2

    rects = [
        # Panel 1 — full-width establisher
        PanelRect(OUTER_MARGIN, top,
                   OUTER_MARGIN + avail_x, top + h1),
        # Panel 2 — left half, row 2
        PanelRect(OUTER_MARGIN, top + h1 + GUTTER,
                   OUTER_MARGIN + half_w, top + h1 + GUTTER + h2),
        # Panel 3 — right half, row 2
        PanelRect(OUTER_MARGIN + half_w + GUTTER, top + h1 + GUTTER,
                   OUTER_MARGIN + avail_x, top + h1 + GUTTER + h2),
        # Panel 4 — full-width, row 3
        PanelRect(OUTER_MARGIN, top + h1 + GUTTER + h2 + GUTTER,
                   OUTER_MARGIN + avail_x,
                   top + h1 + GUTTER + h2 + GUTTER + h3),
        # Panel 5 — full-width, row 4
        PanelRect(OUTER_MARGIN, top + h1 + GUTTER + h2 + GUTTER + h3 + GUTTER,
                   OUTER_MARGIN + avail_x,
                   top + h1 + GUTTER + h2 + GUTTER + h3 + GUTTER + h3),
        # Panel 6 — full-width, row 5
        PanelRect(OUTER_MARGIN,
                   top + h1 + GUTTER + h2 + GUTTER + h3 + GUTTER + h3 + GUTTER,
                   OUTER_MARGIN + avail_x,
                   top + h1 + GUTTER + h2 + GUTTER + h3 + GUTTER + h3 + GUTTER + h3),
    ]

    # Place panels (post-processed for comic look)
    for i, rect in enumerate(rects, start=1):
        panel_img = Image.open(PANEL_DIR / f"panel_{i}.jpg")
        # seed varies per panel for grain
        place_panel(page, panel_img, rect, process=True, seed=42 + i)

    # Header
    draw_page_header(page, fonts,
                     "Star Trek: The Next Generation",
                     "The Last Voice of Kethani", 1, 24)

    # Panel 1 — Captain's Log caption (cyan, italic — Star Trek convention)
    log_balloon = Balloon(
        text='Captain\'s Log, Stardate 47523.6. En route to a distress call '
              'two centuries old.',
        btype=BalloonType.LOG,
        bubble_xy=(rects[0].x0 + 290, rects[0].y0 + 80),
    )
    draw_balloon(page, log_balloon, fonts, dialogue_size=22)

    # Panel 2 — WORF (O.S.) — radio balloon (combadge/intercom)
    # Picard is in the lower-right; bubble in upper-left; tail off-panel-right
    p2 = rects[1]
    worf_balloon = Balloon(
        text='Captain — automated distress signal. '
              'Bearing two-one-seven mark four.',
        speaker='WORF',
        btype=BalloonType.RADIO,    # combadge transmission
        bubble_xy=(p2.x0 + 200, p2.y0 + 110),
        # Off-panel anchor: tail points off the right edge of panel
        anchor_xy=(p2.x1 + 40, p2.y0 + p2.h * 0.4),
        off_panel=True,
    )
    draw_balloon(page, worf_balloon, fonts, dialogue_size=22)

    # Panel 3 — PICARD: "Origin?" and DATA (O.S.) response
    p3 = rects[2]
    picard_balloon = Balloon(
        text='Origin?',
        speaker='PICARD',
        btype=BalloonType.NORMAL,
        bubble_xy=(p3.x0 + 150, p3.y0 + 80),
        # Tail points off-panel-left (Picard is offscreen to the left in panel 3)
        anchor_xy=(p3.x0 - 30, p3.y0 + p3.h * 0.5),
        off_panel=True,
    )
    draw_balloon(page, picard_balloon, fonts, dialogue_size=22)

    data_balloon = Balloon(
        text='Three light years distant, sir. Configuration unknown.',
        speaker='DATA',
        btype=BalloonType.RADIO,
        bubble_xy=(p3.x0 + p3.w // 2, p3.y0 + 230),
        anchor_xy=(p3.x0 - 30, p3.y0 + p3.h * 0.6),
        off_panel=True,
    )
    draw_balloon(page, data_balloon, fonts, dialogue_size=22)

    # Panel 4 — DATA in panel, his dialogue
    p4 = rects[3]
    data_in_panel = Balloon(
        text='Subspace carrier wave degradation suggests it has been '
              'transmitting for a considerable period.',
        speaker='DATA',
        btype=BalloonType.NORMAL,
        bubble_xy=(p4.x0 + 360, p4.y0 + 80),
        # Data is in the lower-center of panel 4 (per our prompt)
        anchor_xy=(p4.x0 + p4.w * 0.5, p4.y0 + p4.h * 0.7),
    )
    draw_balloon(page, data_in_panel, fonts, dialogue_size=22)

    # Panel 5 — RIKER + WORF (O.S.)
    p5 = rects[4]
    riker_balloon = Balloon(
        text='Two centuries. That\'s a long time to wait for rescue.',
        speaker='RIKER',
        btype=BalloonType.NORMAL,
        bubble_xy=(p5.x0 + p5.w * 0.4, p5.y0 + 60),
        # Riker is on the right side of frame in panel 5
        anchor_xy=(p5.x0 + p5.w * 0.78, p5.y0 + p5.h * 0.5),
    )
    draw_balloon(page, riker_balloon, fonts, dialogue_size=22)

    worf_followup = Balloon(
        text='Or a long time for a trap to remain set.',
        speaker='WORF',
        btype=BalloonType.RADIO,
        bubble_xy=(p5.x0 + p5.w * 0.65, p5.y0 + 180),
        anchor_xy=(p5.x1 + 30, p5.y0 + p5.h * 0.6),
        off_panel=True,
    )
    draw_balloon(page, worf_followup, fonts, dialogue_size=22)

    # Panel 6 — PICARD command line
    p6 = rects[5]
    picard_command = Balloon(
        text='Helm, alter course to intercept. Warp six.',
        speaker='PICARD',
        btype=BalloonType.NORMAL,
        bubble_xy=(p6.x0 + p6.w * 0.40, p6.y0 + 60),
        # Picard's silhouette is to the left, viewscreen on the right
        anchor_xy=(p6.x0 + p6.w * 0.20, p6.y0 + p6.h * 0.65),
    )
    draw_balloon(page, picard_command, fonts, dialogue_size=22)

    # Footer
    draw_page_footer(page, fonts)

    page.save(OUT_PATH, "PNG", optimize=True)
    print(f"Saved: {OUT_PATH} ({OUT_PATH.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
