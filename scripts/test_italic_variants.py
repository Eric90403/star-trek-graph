#!/usr/bin/env python3
"""Render three italic variants of Komika Text side-by-side.

Variants:
  A: KOMTXTBI  (Bold Italic — current default)
  B: KOMTXTI_  (regular Italic)
  C: KOMTXTKI  (Kursive Italic — handwritten, more dramatic slant)

Output: data/poc_comic/stage2/italic_variant_compare.png
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from PIL import Image, ImageDraw, ImageFont

VARIANTS = [
    ("A: KOMTXTBI (Bold Italic — current)",  "KOMTXTBI.ttf"),
    ("B: KOMTXTI_ (regular Italic)",           "KOMTXTI_.ttf"),
    ("C: KOMTXTKI (Kursive Italic)",          "KOMTXTKI.ttf"),
]

W, H = 1800, 900
img = Image.new("RGB", (W, H), (210, 210, 210))
draw = ImageDraw.Draw(img)

fonts_dir = Path("/home/eric/projects/star-trek-graph/assets/fonts")
sample_text = "Captain, we are receiving a transmission."
y_cursor = 60
for label, filename in VARIANTS:
    # Label
    draw.text((60, y_cursor), label, font=ImageFont.truetype(
        str(fonts_dir / "KOMTXTB_.ttf"), 28), fill=(20, 20, 30))
    y_cursor += 40
    # Render the sample text in that variant
    font_path = fonts_dir / filename
    try:
        font = ImageFont.truetype(str(font_path), 64)
        draw.text((100, y_cursor), sample_text, font=font, fill=(15, 15, 22))
        y_cursor += 100
    except OSError as e:
        draw.text((100, y_cursor), f"[missing: {e}]", font=ImageFont.load_default(), fill=(180, 30, 30))
        y_cursor += 60

out_path = Path("/home/eric/projects/star-trek-graph/data/poc_comic/stage2/italic_variant_compare.png")
img.save(out_path)
print(f"Saved: {out_path}")
