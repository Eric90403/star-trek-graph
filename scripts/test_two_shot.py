#!/usr/bin/env python3
"""Two-shot test using the chosen C-style anchor (IDW Mike Johnson era).

Scene: TNG bridge, two-shot, Picard (left) speaking to Riker (right).
This is the harder case — the Stage 2 spiral broke on the two-shot
panel (Panel 5). We're verifying the new prompt strategy holds up
when there are multiple characters AND one of them is the speaker
of a dialogue balloon (which will be placed in a later step).

The "one of them is speaking" cue in the prompt is for the model to
give Picard an open-mouth / gesturing pose. The balloon itself will
be added by the placer.

Output: data/poc_comic/stage2/prompt_variants/two_shot_C_picard_speaking.png
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

# Same C-style anchor as the winner, applied to a two-shot scene.
TWO_SHOT_PROMPT = (
    # Core concept — two-shot with a speaker
    "TNG bridge scene, two-shot conversation, Captain Picard on the left "
    "speaking with open mouth and gesturing with one hand, Commander Riker "
    "on the right listening with slight smile and turned toward Picard, "
    "both visible chest-up filling the lower 60% of frame, "
    # Environment
    "TNG bridge set with visible LCARS console displays glowing in soft "
    "blue, starfield on main viewscreen behind both characters, console "
    "rail in foreground, conn and ops stations flanking left and right, "
    # Subject physical attributes
    "Picard bald, dignified, wearing red Starfleet command uniform with "
    "rank insignia, mouth open mid-speech, "
    "Riker bearded, wearing gold Starfleet ops uniform with rank pips, "
    "athletic build, hair pulled back, "
    # Lighting
    "cool blue rim lighting from overhead LCARS panels, warm amber accent "
    "from aft turbolift, soft starfield glow, "
    # Camera
    "cinematic 16:9 composition, medium two-shot, shallow depth of field, "
    # Mood
    "mid-scene dialogue moment, confident command tone, "
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
        "two_shot_C_picard_speaking.png"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Prompt length: {len(TWO_SHOT_PROMPT)} chars")
    print(f"Output: {out_path}")
    result = generate_panel(out_path, TWO_SHOT_PROMPT, style_anchor="",
                            aspect_ratio="16:9")
    print(f"  Cost: ${result['cost_usd']:.4f}")
    print(f"  Time: {result['time_s']}s")
