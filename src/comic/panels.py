#!/usr/bin/env python3
"""
src/comic/panels.py — Panel post-processing to make AI-generated art
read as comic book rather than 'painting'.

Per docs/COMIC_PRODUCTION.md §6:
  1. Posterize (8-12 levels)
  2. Light Canny edge overlay at 30% opacity (gives 'printed ink' feel)
  3. Halftone/screentone overlay (5-10% opacity)
  4. Grain (Gaussian noise 2-4%)
  5. Shared LUT for cross-panel consistency
"""

from __future__ import annotations

import random
from io import BytesIO
from pathlib import Path
from typing import Optional

from PIL import Image, ImageEnhance, ImageFilter, ImageOps


# ── Posterize ─────────────────────────────────────────────────────────────────

def posterize(img: Image.Image, levels: int = 10) -> Image.Image:
    """Reduce color levels per channel — flattens AI gradients into solid
    fills that look like flat cel-shading."""
    return ImageOps.posterize(img.convert("RGB"), bits=int(round(math.log2(levels))) if levels in (2,4,8,16,32,64,128,256) else 4)


# Cleaner approach without bit-counting weirdness
def posterize_simple(img: Image.Image, levels: int = 10) -> Image.Image:
    """Quantize each channel into `levels` bands. levels=10 ≈ comic flat colors."""
    arr = img.convert("RGB").point(lambda p: int(round(p * (levels - 1) / 255)) * (255 // (levels - 1)))
    return arr


# ── Canny-style line overlay ─────────────────────────────────────────────────

def line_overlay(img: Image.Image, opacity: float = 0.30) -> Image.Image:
    """Extract edges and composite back over the image at given opacity.
    Simulates the 'inked line' look of printed comics without needing OpenCV."""
    base = img.convert("RGB")
    # PIL FIND_EDGES produces white-on-black; we want black-on-white
    gray = base.convert("L")
    edges = gray.filter(ImageFilter.FIND_EDGES)
    # Threshold to crisp black lines
    edges = edges.point(lambda p: 0 if p > 40 else 255)
    # Composite: where edge is black (0), darken; otherwise keep base.
    edges_rgb = Image.merge("RGB", (edges, edges, edges))
    return Image.blend(base, edges_rgb, opacity)


# ── Halftone overlay ─────────────────────────────────────────────────────────

def halftone_overlay(img: Image.Image, opacity: float = 0.06,
                      dot_spacing: int = 4) -> Image.Image:
    """Subtle screentone — small dots on midtones."""
    base = img.convert("RGB").copy()
    w, h = base.size
    dot_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    from PIL import ImageDraw
    draw = ImageDraw.Draw(dot_layer)
    for y in range(0, h, dot_spacing):
        for x in range((y // dot_spacing) % 2 * (dot_spacing // 2), w, dot_spacing):
            draw.ellipse((x, y, x + 1, y + 1),
                          fill=(0, 0, 0, int(255 * opacity)))
    base.paste(dot_layer, (0, 0), dot_layer)
    return base


# ── Grain ────────────────────────────────────────────────────────────────────

def add_grain(img: Image.Image, strength: float = 0.03,
              seed: Optional[int] = None) -> Image.Image:
    """Subtle gaussian-ish grain. strength=0.03 ≈ 3% noise."""
    base = img.convert("RGB")
    w, h = base.size
    rng = random.Random(seed)
    px = base.load()
    n_samples = (w * h) // 80
    for _ in range(n_samples):
        x = rng.randint(0, w - 1)
        y = rng.randint(0, h - 1)
        delta = int(rng.gauss(0, 255 * strength))
        r, g, b = px[x, y]
        px[x, y] = (max(0, min(255, r + delta)),
                    max(0, min(255, g + delta)),
                    max(0, min(255, b + delta)))
    return base


# ── Master pipeline ──────────────────────────────────────────────────────────

def to_comic_style(img: Image.Image,
                    posterize_levels: int = 10,
                    line_opacity: float = 0.25,
                    halftone_opacity: float = 0.05,
                    grain_strength: float = 0.025,
                    contrast: float = 1.10,
                    saturation: float = 1.05,
                    seed: Optional[int] = None) -> Image.Image:
    """Apply the full chain. Tuning here matters; see research brief Tier 2."""
    out = img.convert("RGB")
    out = posterize_simple(out, levels=posterize_levels)
    out = line_overlay(out, opacity=line_opacity)
    out = halftone_overlay(out, opacity=halftone_opacity)
    out = ImageEnhance.Contrast(out).enhance(contrast)
    out = ImageEnhance.Color(out).enhance(saturation)
    out = add_grain(out, strength=grain_strength, seed=seed)
    return out


# Need this for posterize() above
import math


__all__ = ["to_comic_style", "posterize_simple", "line_overlay",
            "halftone_overlay", "add_grain"]
