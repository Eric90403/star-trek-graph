#!/usr/bin/env python3
"""Isolated test of the smooth tapered tail on a NORMAL balloon.

Renders 4 balloons with anchors at different relative positions to verify:
  1. Tail is drawn at all
  2. Tail tapers smoothly per Blambot
  3. Tail terminates at 50-60% toward anchor (per BBP §4)
  4. Tail is visible at our 2K source scale

Output: data/poc_comic/stage2/tail_audit.png
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from PIL import Image, ImageDraw

from comic.balloons import Balloon, BalloonType, FontRegistry, draw_balloon

W, H = 2000, 2000
img = Image.new("RGB", (W, H), (200, 200, 200))
fonts = FontRegistry(fonts_dir=Path("/home/eric/projects/star-trek-graph/assets/fonts"))

# Mark each anchor point with a red dot so we can see where the tail
# is supposed to be pointing.
draw = ImageDraw.Draw(img)

# Test 1: balloon upper-left, anchor lower-right (large distance ~700px)
b1_anchor = (1100, 700)
b1 = Balloon(text="Make it so.", speaker="PICARD", btype=BalloonType.NORMAL,
             bubble_xy=(400, 300), anchor_xy=b1_anchor)
draw_balloon(img, b1, fonts, dialogue_size=56)
draw.ellipse((b1_anchor[0]-12, b1_anchor[1]-12, b1_anchor[0]+12, b1_anchor[1]+12),
             fill=(255, 0, 0))
draw.text((1130, 700), "ANCHOR1 (far)", fill=(255, 0, 0))

# Test 2: balloon upper-right, anchor lower-left (large distance)
b2_anchor = (400, 1100)
b2 = Balloon(text="Engage.", speaker="PICARD", btype=BalloonType.NORMAL,
             bubble_xy=(1400, 700), anchor_xy=b2_anchor)
draw_balloon(img, b2, fonts, dialogue_size=56)
draw.ellipse((b2_anchor[0]-12, b2_anchor[1]-12, b2_anchor[0]+12, b2_anchor[1]+12),
             fill=(255, 0, 0))
draw.text((430, 1100), "ANCHOR2 (far)", fill=(255, 0, 0))

# Test 3: balloon center, anchor close (~300px distance)
b3_anchor = (1100, 1700)
b3 = Balloon(text="Two centuries is a long time to wait for rescue.",
             speaker="PICARD", btype=BalloonType.NORMAL,
             bubble_xy=(900, 1400), anchor_xy=b3_anchor)
draw_balloon(img, b3, fonts, dialogue_size=56)
draw.ellipse((b3_anchor[0]-12, b3_anchor[1]-12, b3_anchor[0]+12, b3_anchor[1]+12),
             fill=(255, 0, 0))
draw.text((1130, 1700), "ANCHOR3 (close)", fill=(255, 0, 0))

# Test 4: balloon directly above anchor (vertical tail)
b4_anchor = (1700, 1700)
b4 = Balloon(text="Aye, sir.", speaker="RIKER", btype=BalloonType.NORMAL,
             bubble_xy=(1700, 1350), anchor_xy=b4_anchor)
draw_balloon(img, b4, fonts, dialogue_size=56)
draw.ellipse((b4_anchor[0]-12, b4_anchor[1]-12, b4_anchor[0]+12, b4_anchor[1]+12),
             fill=(255, 0, 0))
draw.text((1730, 1700), "ANCHOR4 (vertical)", fill=(255, 0, 0))

out_path = Path("/home/eric/projects/star-trek-graph/data/poc_comic/stage2/tail_audit.png")
img.save(out_path)
print(f"Saved: {out_path}")
print(f"Test 1: balloon (400,300) → anchor (1100,700), distance ~810px")
print(f"Test 2: balloon (1400,700) → anchor (400,1100), distance ~1080px")
print(f"Test 3: balloon (900,1400) → anchor (1100,1700), distance ~360px")
print(f"Test 4: balloon (1700,1350) → anchor (1700,1700), distance 350px (vertical)")
