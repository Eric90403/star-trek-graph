#!/usr/bin/env python3
"""Wider two-shot test using the chosen C-style anchor (IDW Mike Johnson era).

Same scene as the tight two-shot but with MEDIUM SPACING between
Picard and Riker — clear gap between them, room for a balloon to
sit between their heads. Validates the prompt scales to wider framing.

Output: data/poc_comic/stage2/prompt_variants/two_shot_C_wider.png
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from comic.imagegen import generate_panel

NO_TEXT_SUFFIX = (
    " IMPORTANT: do not include any speech balloons, word balloons, "
    "caption boxes, dialogue text, lettering, sound effects, or written "
    "text of any kind in the image. The panel must contain only the "
    "illustrated scene with no overlaid text or balloons whatsoever."
)

# Wider two-shot: characters with clear separation between them
WIDER_TWO_SHOT_PROMPT = (
    # Core concept — two-shot, WIDER framing
    "TNG bridge scene, two-shot wide composition, Captain Picard on the "
    "left speaking with open mouth and gesturing with one hand, Commander "
    "Riker on the right listening with attentive expression, BOTH VISIBLE "
    "WAIST-UP with clear separation between them, space between their "
    "heads for a speech balloon, "
    # Environment
    "TNG bridge set with visible LCARS console displays glowing in soft "
    "blue, starfield on main viewscreen behind, full bridge layout visible "
    "with conn station on right, ops station on left, captain's chair in "
    "center foreground, "
    # Subject physical attributes
    "Picard bald, dignified, wearing red Starfleet command uniform with "
    "rank insignia on shoulders, mouth open mid-speech, "
    "Riker bearded, wearing gold Starfleet ops uniform with rank pips on "
    "collar, hair pulled back, "
    # Lighting
    "cool blue rim lighting from overhead LCARS panels, warm amber accent "
    "from aft turbolift, soft starfield glow, "
    # Camera
    "cinematic 16:9 composition, medium-wide two-shot, balanced depth of "
    "field keeping both characters in focus, "
    # Mood
    "mid-scene dialogue moment, command briefing tone, "
    # Style anchor — C winner
    "in the style of Mike Johnson and Tony Shasteen's IDW Star Trek "
    "comic run (2009-2018), bright clean coloring, bold black ink linework, "
    "smooth cel-shaded color fills, professional comic art, modern "
    "2009-era Star Trek comic book aesthetic"
    f"{NO_TEXT_SUFFIX}"
)

if __name__ == "__main__":
    out_path = Path(
        "/home/eric/projects/star-trek-graph/data/poc_comic/stage2/prompt_variants/"
        "two_shot_C_wider.png"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Prompt length: {len(WIDER_TWO_SHOT_PROMPT)} chars")
    print(f"Output: {out_path}")
    result = generate_panel(out_path, WIDER_TWO_SHOT_PROMPT, style_anchor="",
                            aspect_ratio="16:9")
    print(f"  Cost: ${result['cost_usd']:.4f}")
    print(f"  Time: {result['time_s']}s")
