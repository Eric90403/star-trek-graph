#!/usr/bin/env python3
"""Build Page 1 of "The Last Voice of Kethani" — 6 panels in 2x3 grid.

Page 1 narrative beats (from data/generated_episodes/SAMPLE_TNG_The_Last_Voice_of_Kethani.txt):
  P1 Panel 1: Captain's log caption + ESTABLISHING SHOT — Enterprise at warp
  P1 Panel 2: BRIDGE WIDE — Picard in chair with PADD, Riker + Worf at
              tactical, Data at ops (sets the scene)
  P1 Panel 3: WORF CLOSE-UP — receiving the distress signal alert
  P1 Panel 4: DATA AT OPS — calculating signal age
  P1 Panel 5: PICARD + RIKER TWO-SHOT — "Two centuries" exchange,
              Worf comm interjects with the trap warning
  P1 Panel 6: PICARD ORDERING WARP — "Helm, alter course"

Each panel:
  - Generates art via Recraft V4.1 with C-style anchor + contextual prompt
  - Vision analysis via MiniMax
  - Reading-order placer
  - Renders balloons onto the art

Page composition: 2x3 grid, 1400px page width, ~10px gutters.

Cost: ~$1.75 (6 panels × $0.25 art + 6 vision calls @ ~$0.05 each).
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
from comic.balloons import (
    Balloon, BalloonType, FontRegistry, draw_balloon,
)
from comic.panel_script import PanelScript, ScriptLine, LineType


NO_TEXT_SUFFIX = (
    " IMPORTANT: do not include any speech balloons, word balloons, "
    "caption boxes, dialogue text, lettering, sound effects, or written "
    "text of any kind in the image. The panel must contain only the "
    "illustrated scene with no overlaid text or balloons whatsoever."
)

STYLE_ANCHOR = (
    "in the style of Mike Johnson and Tony Shasteen's IDW Star Trek "
    "comic run (2009-2018), bright clean coloring, bold black ink linework, "
    "smooth cel-shaded color fills, professional comic art, modern "
    "2009-era Star Trek comic book aesthetic"
)


def build_prompt(scene_core, scene_env, characters_desc, lighting, mood,
                 camera="cinematic 16:9 composition, medium shot"):
    """Build a Recraft prompt with the locked-in C-style structure."""
    parts = [
        scene_core,
        scene_env,
        characters_desc,
        lighting,
        camera,
        mood,
        STYLE_ANCHOR,
    ]
    return ", ".join(parts) + NO_TEXT_SUFFIX


# ── PANEL 1: ESTABLISHING — Enterprise at warp ──────────────────────────────

PANEL_1_PROMPT = build_prompt(
    scene_core="USS Enterprise NCC-1701-D (Galaxy class starship) at warp in deep space",
    scene_env="streaming starlines from warp travel, deep space background with distant nebulae and starfields, the elegant saucer-section and warp nacelles of the Galaxy-class ship prominently centered",
    characters_desc="the Enterprise filling 60% of frame, three-quarter angle view showing saucer section and warp nacelles glowing blue",
    lighting="dramatic side lighting from a distant star, deep blue and purple nebula in background, glowing blue warp nacelle plasma, dynamic warp streak trails",
    mood="majestic, cinematic, journey beginning, the Enterprise on a mission",
    camera="dramatic wide establishing shot, three-quarter angle, cinematic 16:9 composition",
)

PANEL_1_SCRIPT = PanelScript(
    scene="The Enterprise approaches the distress signal",
    panel_id="page1_p1",
    lines=[
        ScriptLine(
            order=1, speaker="PICARD",
            text="Captain's log, stardate 47623.2. We have received a distress signal — faint, ancient, originating from a vessel adrift for centuries.",
            line_type=LineType.LOG,
        ),
    ],
)


# ── PANEL 2: BRIDGE WIDE — establishing the bridge crew ────────────────────

PANEL_2_PROMPT = build_prompt(
    scene_core="TNG Enterprise bridge interior, wide establishing shot showing the full bridge crew",
    scene_env="TNG bridge set with the captain's chair center, LCARS console displays glowing in soft blue, the main viewscreen visible at front showing distant starfield",
    characters_desc="Picard seated in the central captain's chair reviewing a PADD, Riker standing beside the tactical station to the right conferring with Worf, Data at the ops console on the left monitoring readings, all positioned in classic TNG bridge layout",
    lighting="cool blue rim lighting from overhead LCARS panels, warm amber accent from aft turbolift, soft glow from console displays, atmospheric bridge ambient",
    mood="quiet competence, mid-mission, routine survey before mystery",
    camera="wide establishing shot, slightly elevated angle showing whole bridge, cinematic 16:9 composition",
)

PANEL_2_SCRIPT = PanelScript(
    scene="Bridge — routine survey",
    panel_id="page1_p2",
    lines=[],  # Establishing shot, no dialogue
)


# ── PANEL 3: WORF CLOSE-UP — receiving the signal ──────────────────────────

PANEL_3_PROMPT = build_prompt(
    scene_core="TNG Enterprise bridge, Worf at the tactical station, medium close-up",
    scene_env="tactical station with red and amber LCARS displays, Worf's console glowing with sensor readouts, bridge background visible behind him with crew at distant stations",
    characters_desc="Lieutenant Worf, Klingon forehead ridges visible, dignified Klingon warrior, wearing gold Starfleet command/security uniform with sash, looking down at his console with focused attention, alert expression as he detects the signal",
    lighting="amber and red tactical console glow on Worf's face, cool blue ambient bridge lighting, dramatic side lighting emphasizing Worf's intensity",
    mood="alert, focused, the moment of discovery",
    camera="medium close-up of Worf at tactical, shoulder-up framing, dramatic angle",
)

PANEL_3_SCRIPT = PanelScript(
    scene="Worf detects the distress signal",
    panel_id="page1_p3",
    lines=[
        ScriptLine(
            order=1, speaker="WORF",
            text="Captain, we are receiving an automated distress signal. Bearing two-one-seven mark four.",
        ),
    ],
    speaker_positions={"WORF": "center"},
)


# ── PANEL 4: DATA AT OPS — calculating signal age ──────────────────────────

PANEL_4_PROMPT = build_prompt(
    scene_core="TNG Enterprise bridge, Lieutenant Commander Data at the operations console, medium shot",
    scene_env="ops console with multiple LCARS readouts and scientific displays, bridge background visible with viewscreen showing distant point of light against starfield",
    characters_desc="Lieutenant Commander Data, pale android skin tone, yellow Starfleet operations uniform, calm focused expression, hands working at the ops console, scientific concentration",
    lighting="cool blue console glow illuminating Data's pale features, soft bridge ambient, slight golden highlights on Data's uniform",
    mood="analytical, calculating, scientific discovery",
    camera="medium shot of Data at ops console, three-quarter angle, cinematic 16:9 composition",
)

PANEL_4_SCRIPT = PanelScript(
    scene="Data calculates the signal age",
    panel_id="page1_p4",
    lines=[
        ScriptLine(
            order=1, speaker="DATA",
            text="The signal has been transmitting for approximately two hundred seventeen years, sir.",
        ),
    ],
    speaker_positions={"DATA": "center"},
)


# ── PANEL 5: PICARD + RIKER TWO-SHOT + Worf comm ───────────────────────────

PANEL_5_PROMPT = build_prompt(
    scene_core="TNG bridge scene, two-shot wide composition, Captain Picard on the left and Commander Riker on the right",
    scene_env="TNG bridge set with visible LCARS console displays glowing in soft blue, starfield on main viewscreen behind, full bridge layout with conn station on right, ops station on left, captain's chair in center foreground",
    characters_desc="Picard bald, dignified, wearing red Starfleet command uniform with rank insignia, contemplating with thoughtful expression, Riker bearded, wearing gold Starfleet ops uniform with rank pips, leaning toward Picard with concerned reaction, both visible waist-up with clear separation",
    lighting="cool blue rim lighting from overhead LCARS panels, warm amber accent from aft turbolift, soft starfield glow from viewscreen behind",
    mood="contemplative tension, the weight of an ancient mystery",
    camera="medium-wide two-shot, balanced depth of field, cinematic 16:9 composition",
)

PANEL_5_SCRIPT = PanelScript(
    scene="Picard and Riker react; Worf warns",
    panel_id="page1_p5",
    lines=[
        ScriptLine(
            order=1, speaker="RIKER",
            text="Two centuries. That's a long time to wait for rescue.",
        ),
        ScriptLine(
            order=2, speaker="WORF",
            text="Or a long time for a trap to remain set, sir.",
            line_type=LineType.RADIO, off_panel=True, listener="PICARD",
        ),
    ],
    speaker_positions={"PICARD": "left", "RIKER": "right"},
)


# ── PANEL 6: PICARD COMMANDS — closing beat ────────────────────────────────

PANEL_6_PROMPT = build_prompt(
    scene_core="TNG Enterprise bridge, Captain Picard standing decisively giving an order, medium close-up",
    scene_env="TNG bridge with captain's chair visible in background, LCARS displays glowing, viewscreen visible behind showing distant target point in starfield",
    characters_desc="Captain Picard, bald and dignified, red Starfleet command uniform with rank insignia, standing in command posture, hand raised slightly in a gesture of command authority, decisive expression as he gives the order",
    lighting="dramatic cool blue rim lighting emphasizing command presence, warm amber accent from rear bridge",
    mood="decisive command, captain making a course-changing decision, weight of leadership",
    camera="medium close-up at slight low angle (heroic framing), three-quarter view, cinematic 16:9 composition",
)

PANEL_6_SCRIPT = PanelScript(
    scene="Picard commands the course change",
    panel_id="page1_p6",
    lines=[
        ScriptLine(
            order=1, speaker="PICARD",
            text="A reasonable caution, Mister Worf. Helm, alter course to intercept. Warp six.",
        ),
    ],
    speaker_positions={"PICARD": "center"},
)


PANELS = [
    ("p1", PANEL_1_PROMPT, PANEL_1_SCRIPT),
    ("p2", PANEL_2_PROMPT, PANEL_2_SCRIPT),
    ("p3", PANEL_3_PROMPT, PANEL_3_SCRIPT),
    ("p4", PANEL_4_PROMPT, PANEL_4_SCRIPT),
    ("p5", PANEL_5_PROMPT, PANEL_5_SCRIPT),
    ("p6", PANEL_6_PROMPT, PANEL_6_SCRIPT),
]


# ── Per-panel rendering pipeline ────────────────────────────────────────────

def generate_panel_art(name, prompt, out_dir, force_regen=False):
    """Generate one panel's art with Recraft."""
    out_path = out_dir / f"{name}_ART.png"
    if out_path.exists() and not force_regen:
        print(f"  [{name}] cached: {out_path}")
        return out_path
    print(f"  [{name}] generating art ({len(prompt)} char prompt)...")
    result = generate_panel(out_path, prompt, style_anchor="", aspect_ratio="16:9")
    print(f"  [{name}] saved: {out_path} (${result['cost_usd']:.4f}, {result['time_s']}s)")
    return out_path


def render_panel(name, art_path, script, out_dir):
    """Run vision + placer + render for one panel."""
    print(f"\n  [{name}] === Rendering ===")

    # If the script has no dialogue, just copy the art to FINAL
    if not script.lines:
        from shutil import copyfile
        final_path = out_dir / f"{name}_FINAL.png"
        copyfile(art_path, final_path)
        print(f"  [{name}] no dialogue — copied art to {final_path}")
        return final_path

    # Vision analysis (with retry on parse error)
    print(f"  [{name}] vision analysis...")
    try:
        analysis = analyze_panel(art_path)
    except ValueError as e:
        print(f"  [{name}] vision parse failed, retrying with stricter prompt...")
        # Retry once — minimax sometimes complies on second attempt
        try:
            analysis = analyze_panel(art_path)
        except ValueError as e2:
            print(f"  [{name}] vision retry also failed: {e2}")
            print(f"  [{name}] copying art as fallback (no balloons placed)")
            from shutil import copyfile
            final_path = out_dir / f"{name}_FINAL.png"
            copyfile(art_path, final_path)
            return final_path
    print(f"  [{name}] faces={len(analysis.face_bboxes)}, empty_regions={len(analysis.empty_regions)}")

    panel_bbox = (0, 0, analysis.width, analysis.height)

    # Place balloons
    print(f"  [{name}] placing balloons...")
    try:
        placements = place_balloons_for_panel(panel_bbox, analysis, script)
    except PlacementError as e:
        print(f"  [{name}] PLACEMENT FAILED: {e}")
        # Fallback: copy art so we can still see the page
        from shutil import copyfile
        final_path = out_dir / f"{name}_FINAL.png"
        copyfile(art_path, final_path)
        return final_path

    for line, p in zip(script.sorted_lines(), placements):
        print(f"  [{name}]   L{line.order} {line.speaker}: cx={p.cx}, cy={p.cy}, score={p.score:.1f}")

    # Render balloons onto art
    print(f"  [{name}] rendering balloons...")
    img = Image.open(art_path).convert("RGB")
    fonts = FontRegistry(fonts_dir=Path("/home/eric/projects/star-trek-graph/assets/fonts"))

    face_tops = [((f[0] + f[2]) / 2, f[1]) for f in analysis.face_bboxes]

    def speaker_face_for(line):
        if line.line_type == LineType.RADIO:
            return None
        if not face_tops:
            return None
        if script.speaker_positions and line.speaker in script.speaker_positions:
            pos = script.speaker_positions[line.speaker]
            if pos == "left":
                return min(face_tops, key=lambda c: c[0])
            elif pos == "right":
                return max(face_tops, key=lambda c: c[0])
        return min(face_tops, key=lambda c: c[0])

    for line, placement in zip(script.sorted_lines(), placements):
        if line.line_type == LineType.LOG:
            btype = BalloonType.LOG
        elif line.line_type == LineType.RADIO:
            btype = BalloonType.RADIO
        elif line.line_type == LineType.CAPTION:
            btype = BalloonType.CAPTION
        else:
            btype = BalloonType.NORMAL
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

    final_path = out_dir / f"{name}_FINAL.png"
    img.save(final_path)
    print(f"  [{name}] saved: {final_path}")
    return final_path


def compose_page(panel_paths, out_path, page_width=1400):
    """Compose all 6 panels into a 2x3 grid Page 1.

    Page format per docs/COMIC_PRODUCTION.md:
      - Canvas width 1400px
      - Aspect ratio 1:1.547 → page height 2168px
      - 2x3 grid with 20px gutters
      - 50px outer page margin
    """
    PAGE_W = page_width
    PAGE_H = int(page_width * 1.547)
    OUTER_MARGIN = 50
    GUTTER = 20

    # Grid: 2 columns × 3 rows
    inner_w = PAGE_W - 2 * OUTER_MARGIN
    inner_h = PAGE_H - 2 * OUTER_MARGIN
    panel_w = (inner_w - GUTTER) // 2
    # Panel aspect 16:9 → each panel height = panel_w * 9/16
    panel_h_aspect = int(panel_w * 9 / 16)
    # Three rows of panels with gutters
    total_panel_h = 3 * panel_h_aspect + 2 * GUTTER
    # Center vertically if there's extra space
    y_offset = OUTER_MARGIN + max(0, (inner_h - total_panel_h) // 2)

    page = Image.new("RGB", (PAGE_W, PAGE_H), (255, 255, 255))
    draw = ImageDraw.Draw(page)

    for i, panel_path in enumerate(panel_paths):
        row = i // 2
        col = i % 2
        x = OUTER_MARGIN + col * (panel_w + GUTTER)
        y = y_offset + row * (panel_h_aspect + GUTTER)
        # Load and resize panel to fit
        img = Image.open(panel_path).convert("RGB")
        img_resized = img.resize((panel_w, panel_h_aspect), Image.LANCZOS)
        page.paste(img_resized, (x, y))
        # Draw panel border
        draw.rectangle((x, y, x + panel_w, y + panel_h_aspect),
                       outline=(0, 0, 0), width=3)

    page.save(out_path)
    print(f"\n=== Page composed: {out_path} ({PAGE_W}x{PAGE_H}) ===")
    return out_path


if __name__ == "__main__":
    out_dir = Path("/home/eric/projects/star-trek-graph/data/poc_comic/stage3")
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=== PAGE 1 GENERATION ===")
    print(f"Output dir: {out_dir}")

    # Step 1: Generate art for all 6 panels (parallelizable but sequential
    # for clarity)
    print("\n--- Step 1: Generate panel art ---")
    art_paths = {}
    for name, prompt, _ in PANELS:
        art_paths[name] = generate_panel_art(name, prompt, out_dir)

    # Step 2: Run vision + placer + render on each panel
    print("\n--- Step 2: Render each panel with balloons ---")
    final_paths = []
    for name, _, script in PANELS:
        final = render_panel(name, art_paths[name], script, out_dir)
        final_paths.append(final)

    # Step 3: Compose the page
    print("\n--- Step 3: Compose Page 1 ---")
    page_path = out_dir / "PAGE_1.png"
    compose_page(final_paths, page_path)

    print(f"\n=== DONE ===")
    print(f"Page 1: {page_path}")
    print(f"Panels: {final_paths}")
