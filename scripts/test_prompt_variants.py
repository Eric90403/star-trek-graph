#!/usr/bin/env python3
"""Task 5: 3-variant Recraft prompt test matrix.

Per data/COMIC_PIPELINE_DESIGN.md §8 and §9 (renumbered; see file for §N),
generate 3 art variants for the same Panel 2 scene (Picard at command
chair, contemplative moment) using different prompt strategies:

  Variant A: BASELINE — current prompt with "negative space" language.
              Expected: vast white void, characters small in frame.
              (Reproduces the broken Stage 2 spiral output for comparison.)

  Variant B: DENSE ATMOSPHERE — structured global-to-local prompt per
              Recraft V4 guide. Kills "negative space" language. Adds
              composition density directives, bridge set dressing,
              lighting specifics. (BBP §6)

  Variant C: DENSE + STYLE ANCHOR — Same as B plus explicit "Mike
              Johnson era IDW Star Trek 2009-2018" style reference.
              Risk: over-fitting to one artist's style.

Eric reviews all 3 and picks direction. Cost: ~$0.75 (3 × $0.25).

Output: data/poc_comic/stage2/prompt_variants/variant_{A,B,C}.png
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from comic.imagegen import generate_panel, HOUSE_STYLE


# Scene: Panel 2 from "The Last Voice of Kethani" — Picard alone at
# command chair, contemplative moment, ready for Worf comm to interrupt.
# This is the same scene that produced the broken Stage 2 output we
# are trying to fix.

SCENE = "TNG bridge, Captain Picard standing at command chair"

# Common negative-text suffix (preserved across all variants to prevent
# Recraft from drawing its own balloons).
NO_TEXT_SUFFIX = (
    " IMPORTANT: do not include any speech balloons, word balloons, "
    "caption boxes, dialogue text, lettering, sound effects, or written "
    "text of any kind in the image. The panel must contain only the "
    "illustrated scene with no overlaid text or balloons whatsoever."
)


# ── Variant A: BASELINE (current broken approach) ────────────────────────────
# Reproduces the prompt style that produced the white-void outputs in
# the Stage 2 spiral. The "negative space" language tells Recraft to
# leave the panel empty.

VARIANT_A_PROMPT = (
    f"{SCENE}, contemplative moment, looking at viewscreen, "
    "wide shot showing bridge environment with negative space in upper "
    "portion of frame for speech balloon placement. Leave empty area at "
    "top of panel for text overlay. Simple, clean background. "
    f"{HOUSE_STYLE}{NO_TEXT_SUFFIX}"
)


# ── Variant B: DENSE ATMOSPHERE (no negative space) ─────────────────────────
# Per Recraft V4 guide: structured global-to-local prompt. Composition
# density directives replace the "leave space" language. Specific
# environmental and lighting cues.

VARIANT_B_PROMPT = (
    # 1. Core concept
    f"{SCENE}, Picard standing at command chair, contemplative moment, "
    # 2. Background/environment — fill the frame with bridge atmosphere
    "TNG bridge set with visible LCARS console displays glowing in soft blue, "
    "starfield on main viewscreen behind, console rail in foreground, "
    "conn and ops stations visible in background, "
    # 3. Primary subject framing — NO negative space
    "Picard positioned chest-up filling lower 50-60% of frame, "
    "command chair and bridge environment filling the rest of the composition, "
    # 4. Physical attributes
    "Picard bald, dignified expression, hands clasped behind back, "
    "wearing red Starfleet command uniform with rank insignia, "
    # 5. Lighting
    "cool blue rim lighting from overhead LCARS panels, "
    "warm amber accent light from aft turbolift, "
    "soft starfield glow from viewscreen, "
    # 6. Camera
    "cinematic 16:9 composition, medium shot, shallow depth of field, "
    # 7. Mood
    "quiet authority, mid-scene contemplative moment, "
    # 8. Style anchor (kept from current)
    f"{HOUSE_STYLE}{NO_TEXT_SUFFIX}"
)


# ── Variant C: DENSE + STYLE ANCHOR (most specific) ────────────────────────
# Same as B but with explicit "Mike Johnson era IDW Star Trek" reference.
# Mike Johnson + Tony Shasteen ran IDW Star Trek 2009-2018. Risk: model
# may over-fit to one artist's interpretation.

VARIANT_C_PROMPT = (
    # 1. Core concept
    f"{SCENE}, Picard standing at command chair, contemplative moment, "
    # 2. Background/environment
    "TNG bridge set with visible LCARS console displays glowing in soft blue, "
    "starfield on main viewscreen behind, console rail in foreground, "
    "conn and ops stations visible in background, "
    # 3. Primary subject framing
    "Picard positioned chest-up filling lower 50-60% of frame, "
    "command chair and bridge environment filling the rest of the composition, "
    # 4. Physical attributes
    "Picard bald, dignified expression, hands clasped behind back, "
    "wearing red Starfleet command uniform with rank insignia, "
    # 5. Lighting
    "cool blue rim lighting from overhead LCARS panels, "
    "warm amber accent light from aft turbolift, "
    "soft starfield glow from viewscreen, "
    # 6. Camera
    "cinematic 16:9 composition, medium shot, shallow depth of field, "
    # 7. Mood
    "quiet authority, mid-scene contemplative moment, "
    # 8. STYLE ANCHOR — explicit IDW era reference
    "in the style of Mike Johnson and Tony Shasteen's IDW Star Trek "
    "comic run (2009-2018), bright clean coloring, bold black ink linework, "
    "smooth cel-shaded color fills, professional comic art, "
    "modern 2009-era Star Trek comic book aesthetic"
    f"{NO_TEXT_SUFFIX}"
)


VARIANTS = [
    ("A_baseline_negative_space", VARIANT_A_PROMPT),
    ("B_dense_atmosphere",         VARIANT_B_PROMPT),
    ("C_dense_with_style_anchor",  VARIANT_C_PROMPT),
]


if __name__ == "__main__":
    out_dir = Path("/home/eric/projects/star-trek-graph/data/poc_comic/stage2/prompt_variants")
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for name, prompt in VARIANTS:
        out_path = out_dir / f"variant_{name}.png"
        print(f"\n=== Generating variant {name} ===")
        print(f"Prompt length: {len(prompt)} chars")
        print(f"Output: {out_path}")
        result = generate_panel(out_path, prompt, style_anchor="",  # style_anchor is in prompt
                                aspect_ratio="16:9")
        print(f"  Cost: ${result['cost_usd']:.4f}")
        print(f"  Time: {result['time_s']}s")
        results.append((name, out_path, result["cost_usd"]))

    total = sum(c for _, _, c in results)
    print(f"\n=== Total: ${total:.4f} for {len(results)} variants ===")
    for name, path, cost in results:
        print(f"  {name}: {path} (${cost:.4f})")
