#!/usr/bin/env python3
"""Task 6: Regenerate Panel 2 + Panel 5 with the locked-in C-style anchor.

Per the handoff:
  Panel 2: Picard alone (at command chair) + Worf comm (off-panel).
  Panel 5: Picard + Riker two-shot (conversing) + Worf comm (off-panel).

These are the two panels the Stage 2 spiral was working on. We
regenerate them with the new C-style prompt template so the art is
the foundation we validate everything else against (per the §0
priority callout in COMIC_PIPELINE_DESIGN.md).

Output: data/poc_comic/stage2/panel_2_FINAL.png
        data/poc_comic/stage2/panel_5_FINAL.png

Cost: ~$0.50 (2 × $0.25).
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

# ── Panel 2: Picard alone at command chair ──────────────────────────────────
# Scene matches Stage 2's Panel 2: Picard standing or seated at command
# chair, contemplative moment, ready to receive a Worf comm.

PANEL_2_PROMPT = (
    # Core concept
    "TNG bridge scene, single character medium-close shot, Captain Picard "
    "at the command chair, contemplative expression, looking at the main "
    "viewscreen, "
    # Environment
    "TNG bridge set with visible LCARS console displays glowing in soft "
    "blue, starfield on main viewscreen behind, console rail in foreground, "
    "conn and ops stations visible in background, "
    # Subject physical attributes
    "Picard bald, dignified, wearing red Starfleet command uniform with "
    "rank insignia on shoulders, hands clasped in front, "
    # Lighting
    "cool blue rim lighting from overhead LCARS panels, warm amber accent "
    "from aft turbolift, soft starfield glow, "
    # Camera
    "cinematic 16:9 composition, medium close-up, shallow depth of field, "
    # Mood
    "quiet authority, mid-scene contemplative moment, "
    # Style anchor — locked in C
    "in the style of Mike Johnson and Tony Shasteen's IDW Star Trek "
    "comic run (2009-2018), bright clean coloring, bold black ink linework, "
    "smooth cel-shaded color fills, professional comic art, modern "
    "2009-era Star Trek comic book aesthetic"
    f"{NO_TEXT_SUFFIX}"
)


# ── Panel 5: Picard + Riker two-shot + Worf comm ───────────────────────────
# WIDER framing than the tight two-shot test — characters have clear
# separation, room for balloons above and between them. This is the
# case the Stage 2 spiral failed on; we need balloon placement room.

PANEL_5_PROMPT = (
    # Core concept
    "TNG bridge scene, two-shot wide composition, Captain Picard on the "
    "left speaking with open mouth and gesturing, Commander Riker on the "
    "right listening attentively, BOTH VISIBLE WAIST-UP with clear "
    "separation between them, space above and between their heads for "
    "speech balloons, "
    # Environment
    "TNG bridge set with visible LCARS console displays glowing in soft "
    "blue, starfield on main viewscreen behind, full bridge layout with "
    "conn station on right, ops station on left, captain's chair in "
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
    # Style anchor — locked in C
    "in the style of Mike Johnson and Tony Shasteen's IDW Star Trek "
    "comic run (2009-2018), bright clean coloring, bold black ink linework, "
    "smooth cel-shaded color fills, professional comic art, modern "
    "2009-era Star Trek comic book aesthetic"
    f"{NO_TEXT_SUFFIX}"
)


PANELS = [
    ("panel_2", PANEL_2_PROMPT, "Picard alone + Worf comm"),
    ("panel_5", PANEL_5_PROMPT, "Picard + Riker two-shot + Worf comm"),
]


if __name__ == "__main__":
    out_dir = Path("/home/eric/projects/star-trek-graph/data/poc_comic/stage2")
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for name, prompt, desc in PANELS:
        out_path = out_dir / f"{name}_FINAL.png"
        print(f"\n=== Generating {name} ({desc}) ===")
        print(f"Prompt length: {len(prompt)} chars")
        print(f"Output: {out_path}")
        result = generate_panel(out_path, prompt, style_anchor="",
                                aspect_ratio="16:9")
        print(f"  Cost: ${result['cost_usd']:.4f}")
        print(f"  Time: {result['time_s']}s")
        results.append((name, out_path, result["cost_usd"]))

    total = sum(c for _, _, c in results)
    print(f"\n=== Total: ${total:.4f} for {len(results)} panels ===")
    for name, path, cost in results:
        print(f"  {name}: {path} (${cost:.4f})")
