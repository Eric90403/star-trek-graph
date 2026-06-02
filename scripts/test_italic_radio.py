#!/usr/bin/env python3
"""Quick test render of the new italic-body radio balloon.

Renders two sample radio balloons (short and long) onto a neutral grey
background, so we can visually confirm:
  1. Inline speaker tag ("WORF VIA COMMS:" / "DATA VIA COMMS:") is in
     non-italic red
  2. Body text is in italic black
  3. Double outline is visible
  4. No tail
  5. Text is readable and fits the balloon
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from PIL import Image

from comic.balloons import Balloon, BalloonType, FontRegistry, draw_balloon

# Blank neutral-grey canvas so the white balloon body shows clearly
W, H = 1600, 1400
img = Image.new("RGB", (W, H), (200, 200, 200))

fonts = FontRegistry(fonts_dir=Path("/home/eric/projects/star-trek-graph/assets/fonts"))

# Test 1: Short line, upper area
b1 = Balloon(
    text="Captain, we are receiving a transmission from Starfleet Command.",
    speaker="WORF",
    btype=BalloonType.RADIO,
    bubble_xy=(W // 2, 280),
)
draw_balloon(img, b1, fonts, dialogue_size=56)

# Test 2: Long line that should wrap, well below test 1
b2 = Balloon(
    text="The away team reports the anomaly is expanding faster than predicted. Recommend immediate evacuation of the research station.",
    speaker="DATA",
    btype=BalloonType.RADIO,
    bubble_xy=(W // 2, 900),
)
draw_balloon(img, b2, fonts, dialogue_size=56)

out_path = Path("/home/eric/projects/star-trek-graph/data/poc_comic/stage2/italic_radio_test.png")
out_path.parent.mkdir(parents=True, exist_ok=True)
img.save(out_path)
print(f"Saved: {out_path}")
print(f"Size: {out_path.stat().st_size} bytes")
