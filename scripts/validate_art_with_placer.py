#!/usr/bin/env python3
"""Task 7: validate regenerated art with the new reading-order placer.

For each panel art (panel_2_FINAL.png, panel_5_FINAL.png):
  1. Run vision analysis (Opus via OpenRouter, ~$0.10/panel)
  2. Build a PanelScript matching the scene
  3. Run place_balloons_for_panel (the new reading-order placer)
  4. Render balloons onto the art
  5. Save _FINAL.png (with balloons) and _DEBUG.png (with bbox overlays)

If output looks good, we proceed to building the full 6-panel page
for "The Last Voice of Kethani".

Output:
  data/poc_comic/stage2/panel_2_FINAL.png  (replaced with version w/ balloons)
  data/poc_comic/stage2/panel_5_FINAL.png  (replaced with version w/ balloons)
  data/poc_comic/stage2/panel_2_DEBUG.png  (NEW — bbox overlays)
  data/poc_comic/stage2/panel_5_DEBUG.png  (NEW)
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from PIL import Image, ImageDraw

from comic.imagegen import generate_panel
from comic.intelligence import (
    analyze_panel,
    place_balloons_for_panel,
    analysis_summary,
    PanelAnalysis,
    PlacementError,
)
from comic.balloons import Balloon, BalloonType, FontRegistry, draw_balloon
from comic.panel_script import PanelScript, ScriptLine, LineType


# ── Panel 2: Picard alone + Worf comm ────────────────────────────────────────
# The handoff's Panel 2 scene: Picard speaking, then a Worf-via-comms reply.
# Art is already cached at panel_2_FINAL.png (from Task 6, ~16s to gen).

PANEL_2_ART = Path("/home/eric/projects/star-trek-graph/data/poc_comic/stage2/panel_2_ART.png")
PANEL_2_SCRIPT = PanelScript(
    scene="Bridge — Captain muses on a long-abandoned distress call",
    panel_id="page1_panel2",
    lines=[
        ScriptLine(
            order=1, speaker="PICARD",
            text="Two centuries. That is a long time to wait for rescue.",
        ),
        ScriptLine(
            order=2, speaker="WORF",
            text="Or a long time for a trap to remain set, sir.",
            line_type=LineType.RADIO, off_panel=True, listener="PICARD",
        ),
    ],
)


# ── Panel 5: Picard + Riker two-shot + Worf comm ───────────────────────────
# The spiral's broken case. Picard and Riker visible, then Worf comms in.

PANEL_5_ART = Path("/home/eric/projects/star-trek-graph/data/poc_comic/stage2/panel_5_ART.png")
PANEL_5_SCRIPT = PanelScript(
    scene="Bridge — Picard and Riker discussing the signal",
    panel_id="page1_panel5",
    lines=[
        ScriptLine(
            order=1, speaker="PICARD",
            text="Two centuries. That is a long time to wait for rescue.",
        ),
        ScriptLine(
            order=2, speaker="RIKER",
            text="Or a long time for a trap to remain set, sir.",
        ),
        ScriptLine(
            order=3, speaker="WORF",
            text="Captain, I am detecting an anomaly on long-range sensors.",
            line_type=LineType.RADIO, off_panel=True, listener="PICARD",
        ),
    ],
    speaker_positions={"PICARD": "left", "RIKER": "right"},
)


def render_panel_with_script(
    art_path: Path,
    script: PanelScript,
    out_final: Path,
    out_debug: Path,
) -> dict:
    """Run the full pipeline: vision → placer → render. Save final + debug.

    Process invariant: art_path is READ-ONLY. We never write back to it.
    out_final and out_debug are derived outputs. This separation is the
    fix for the bug in the prior session where the validate script
    overwrote panel_X_FINAL.png with the balloon-rendered version,
    contaminating the source for subsequent reruns.
    """
    assert art_path != out_final, (
        f"art_path must be distinct from out_final to prevent source "
        f"contamination. Got art_path={art_path}, out_final={out_final}"
    )
    print(f"\n=== Processing {art_path.name} ===")
    print(f"  Source art: {art_path}")
    print(f"  Output final: {out_final}")
    print(f"  Output debug: {out_debug}")

    # 1. Vision analysis
    print("  [1/4] Vision analysis...")
    analysis = analyze_panel(art_path)
    print(analysis_summary(analysis))

    panel_w, panel_h = analysis.width, analysis.height
    panel_bbox = (0, 0, panel_w, panel_h)

    # 2. Place balloons using the new reading-order placer
    print("  [2/4] Placing balloons (reading-order algorithm)...")
    try:
        placements = place_balloons_for_panel(panel_bbox, analysis, script)
        for i, (line, p) in enumerate(zip(script.sorted_lines(), placements)):
            print(f"    line {line.order} ({line.speaker:8s}): "
                  f"cx={p.cx:4d} cy={p.cy:4d} score={p.score:7.1f} rect={p.rect}")
    except PlacementError as e:
        print(f"    PLACEMENT FAILED: {e}")
        print(f"    panel_bbox={panel_bbox}, faces={analysis.face_bboxes}")
        print(f"    line that failed: order={e.line_order} speaker={e.line_speaker}")
        raise

    # 3. Render balloons onto the art
    print("  [3/4] Rendering balloons onto art...")
    img = Image.open(art_path).convert("RGB")
    fonts = FontRegistry(fonts_dir=Path("/home/eric/projects/star-trek-graph/assets/fonts"))

    # Identify speaker face TOPS for tail anchors. Using face_top (not
    # face_center) per design: the tail terminates at upper-forehead,
    # well outside the eye/mouth area. Sources:
    # data/COMIC_TECHNIQUES_RESEARCH.md §5 q2.
    face_tops = [((f[0] + f[2]) / 2, f[1])
                 for f in analysis.face_bboxes]

    def speaker_face_for(line):
        """Get the speaker's face TOP for tail anchor (NORMAL only)."""
        if line.line_type == LineType.RADIO:
            return None  # No tail on radio balloons
        if not face_tops:
            return None
        if script.speaker_positions and line.speaker in script.speaker_positions:
            pos = script.speaker_positions[line.speaker]
            if pos == "left":
                return min(face_tops, key=lambda c: c[0])
            elif pos == "right":
                return max(face_tops, key=lambda c: c[0])
        return min(face_tops, key=lambda c: c[0])  # leftmost default

    for line, placement in zip(script.sorted_lines(), placements):
        btype = BalloonType.RADIO if line.line_type == LineType.RADIO else BalloonType.NORMAL
        anchor = speaker_face_for(line)
        balloon = Balloon(
            text=line.text,
            speaker=line.speaker,
            btype=btype,
            bubble_xy=(placement.cx, placement.cy),
            anchor_xy=anchor,
            off_panel=line.off_panel,
        )
        draw_balloon(img, balloon, fonts, dialogue_size=56)

    img.save(out_final)
    print(f"    saved: {out_final}")

    # 4. Build debug overlay showing face bboxes + balloon bboxes
    print("  [4/4] Building debug overlay...")
    debug_img = Image.open(art_path).convert("RGB")
    ddraw = ImageDraw.Draw(debug_img, "RGBA")
    # Faces in red
    for fx0, fy0, fx1, fy1 in analysis.face_bboxes:
        ddraw.rectangle((fx0, fy0, fx1, fy1), outline=(255, 0, 0, 255), width=4)
    # Placements in green
    for i, (line, p) in enumerate(zip(script.sorted_lines(), placements)):
        ddraw.rectangle(p.rect, outline=(0, 255, 0, 255), width=3)
        # Label with line.order
        ddraw.text((p.rect[0] + 4, p.rect[1] + 4),
                   f"L{line.order}:{line.speaker}", fill=(0, 200, 0, 255))
    debug_img.save(out_debug)
    print(f"    saved: {out_debug}")

    return {
        "placements": len(placements),
        "vision_cost": 0.10,  # approximate, see analyze_panel
    }


if __name__ == "__main__":
    stage2 = Path("/home/eric/projects/star-trek-graph/data/poc_comic/stage2")

    # Panel 2 — read from _ART.png, write to _FINAL.png (separate files).
    p2_final = stage2 / "panel_2_FINAL.png"
    p2_debug = stage2 / "panel_2_DEBUG.png"
    render_panel_with_script(PANEL_2_ART, PANEL_2_SCRIPT, p2_final, p2_debug)

    # Panel 5 — read from _ART.png, write to _FINAL.png (separate files).
    p5_final = stage2 / "panel_5_FINAL.png"
    p5_debug = stage2 / "panel_5_DEBUG.png"
    render_panel_with_script(PANEL_5_ART, PANEL_5_SCRIPT, p5_final, p5_debug)

    print("\n=== Done ===")
    print(f"  Final:  {p2_final}, {p5_final}")
    print(f"  Debug:  {p2_debug}, {p5_debug}")
