# Comic Pipeline Design Proposal — v1

**Date:** 2026-06-02
**Status:** DRAFT — pending Eric's review and sign-off before any code
**Author:** Hermes
**Companion docs:**
- `data/STAGE2_REVISED_PLAN.md` — the operational plan (Phases 1-5)
- `data/COMIC_BEST_PRACTICES.md` — the rules this design implements
- `docs/COMIC_PRODUCTION.md` — broader research brief (production specs)

**Purpose:** Define the code design for Phases 1-5 of the revised plan.
Each design decision cites a specific rule from the best-practices doc
using [BBP §N] notation. No silent decisions.

---

## 1. Design principles (from BBP + Eric's hard rules)

These are the principles that govern the design:

| Principle | Source | What it means for code |
|-----------|--------|------------------------|
| Plan text before art | BBP §2, Rule 9 | Pre-compute text dimensions before balloon position |
| Script order = reading order | BBP §2 | `PanelScript.lines` is the authoritative sequence |
| Faces are sacred | BBP §1, Rule 1 + Eric's Rule 1 | Hard veto, no exceptions except speaker's own face for tail only |
| Speaker on the left speaks first | BBP §2, Rule 3 | Two-shot placer uses character position to bias first balloon |
| Radio balloon has no tail, inline tag conveys speaker | BBP §5 + Eric's Rule 2-3 | Placer ignores anchor for radio balloons |
| Width-retry, not first-fit | BBP §2, Rule 10 | `find_balloon_position()` scores multiple candidates per line |
| No silent iteration | Eric's Rule 6 | Every output is shown before next step; tests verify, not "looks right" |

---

## 2. Data model — `PanelScript`

**New module:** `src/comic/panel_script.py`

```python
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

class LineType(Enum):
    NORMAL = "normal"      # In-person speech
    RADIO  = "radio"       # Combadge/viewscreen/intercom
    SHOUT  = "shout"       # Loud / burst balloon
    WHISPER = "whisper"    # Quiet / dashed outline
    CAPTION = "caption"    # Narration, log entry
    LOG    = "log"         # Captain's Log, cyan italic box

@dataclass
class ScriptLine:
    order: int                       # Reading-order index. 1 = first balloon read.
    speaker: str                     # Canonical character name (e.g. "RIKER")
    text: str                        # The dialogue (without inline tag — added by renderer)
    line_type: LineType = LineType.NORMAL
    off_panel: bool = False          # Speaker not visible in panel
    listener: Optional[str] = None   # For radio: who is receiving (used for context, NOT placement)

@dataclass
class PanelScript:
    scene: str                       # "Bridge - Night Watch"
    panel_id: str                    # For traceability: "page1_panel2"
    lines: List[ScriptLine]          # Authoritative reading order. len ≥ 1.
    # Optional, for two-shot panels: explicit character positions so placer
    # doesn't have to infer from face bboxes (face bboxes are noisy).
    speaker_positions: Optional[dict] = None  # {"PICARD": "left", "RIKER": "right"}
```

**Why this structure:**

- `order` is explicit, not inferred. The placer never has to guess reading
  order — it's in the data. Maps to **BBP §2, Rule 2** (script order = reading order).
- `line_type` carries the radio/normal/caption distinction. The renderer
  uses this to pick the right balloon shape. Maps to **BBP §1, Rule 8**
  (balloon type determines visual treatment).
- `off_panel` is a hint for the renderer (no tail), NOT for the placer
  to find an anchor. Maps to **BBP §5** (no anchor for radio balloons).
- `speaker_positions` optional override for two-shots. The placer can
  infer from face bboxes when not provided, but explicit is better for
  repeatability. Maps to **BBP §2, Rule 3** (left character speaks first).

**Constraint:** `len(lines) >= 1` (a panel without dialogue is a panel of pure
art; we handle that case but it's not the placer's job). Lines must be
unique `order` values — validated at construction.

---

## 3. Reading-order placer — algorithm

**Module:** `src/comic/intelligence.py` (modify existing)

**Public function signature:**

```python
def place_balloons_for_panel(
    panel_image: Image.Image,
    panel_analysis: PanelAnalysis,       # existing vision output
    script: PanelScript,                 # NEW: explicit script
    max_attempts: int = 3,
) -> List[BalloonPlacement]:
    """Place balloons for a panel using script reading order.
    Returns a list of BalloonPlacement objects (one per ScriptLine).
    Raises PlacementError if any balloon cannot be placed safely.
    """
```

**Algorithm (per line, in script order):**

1. **Pre-compute text dimensions** (BBP §2, Rule 9):
   - Render text at known font size, measure width × height
   - This is the balloon's interior size; total size is text + padding

2. **Generate candidate positions** in zones based on line order:
   - **Line 1:** upper-left zone (top 30%, left 60% of panel)
   - **Line 2:** below and/or right of line 1's chosen position
   - **Line 3+:** continue the down-and-right pattern
   - **Single-line panel:** top-center zone
   - For two-speaker two-shots: bias line 1 toward left character,
     line 2 toward right character or below line 1
     (BBP §2, Rule 3)

3. **For each candidate, check hard vetoes (in order):**
   - Panel edge margin (no balloon within 20px of any panel edge)
   - Face overlap (AABB intersection with any face bbox = 0)
   - Tail crosses face (only for non-radio lines)
   - Prior balloon overlap (AABB intersection with placed balloons > 0)
   - Tail crosses tail (only for non-radio lines)
   - Map to **BBP §1, Rules 1, 7** and **§3** (face protection)

4. **For each surviving candidate, compute soft score:**
   - **+ Reading-order zone bonus:** candidate in expected zone for this
     line = +100; outside = -50. Maps to **BBP §2, Rule 2**.
   - **+ Speaker proximity (NORMAL only):** distance from balloon edge
     to speaker's face center, scored up to +300 with falloff.
     Maps to **BBP §1, Rule 4** (tail points at mouth).
   - **+ Empty region bonus:** +10/+25/+50 by quality of nearby empty
     region (existing logic in `find_balloon_position()`).
   - **- Body overlap penalty:** AABB intersection with body bbox = -20 per
     overlapping body. Maps to **BBP §1, Rule 5** (avoid body, but not sacred).
   - **- Off-zone penalty:** balloon drifted too far from expected zone
     = -30.

5. **Width-retry loop** (BBP §2, Rule 10):
   - If no candidate survives at full text width, retry with progressively
     narrower widths (re-wrap text)
   - Pick the highest-scoring width

6. **Pick best candidate. Place it. Move to next line.**

7. **If any line cannot be placed:** return PlacementError with the line
   number and reason. The orchestrator (`render_panel_poc.py`) can then
   decide whether to retry with a wider balloon, edit the script, or
   regenerate the art (composition-guidance addendum).

**Critical: radio balloon path**

For `LineType.RADIO`:
- Step 3: skip the "tail crosses face" check (no tail to draw)
- Step 4: skip the "speaker proximity" score (no anchor). The radio
  balloon's position is determined entirely by reading-order zone +
  empty-region bonus.
- The combadge-anchor computation is **DELETED ENTIRELY**. This is the
  change from the Stage 2 spiral (BBP §5 + Eric's Rule 2-3).

**Critical: tail-crosses-face exemption**

For NORMAL balloons, the "tail crosses face" check exempts the SPEAKER'S
OWN face. The tail points at them — that's correct (BBP §1, Rule 4). The
balloon body itself can never cover the speaker's face (that's the hard
face-overlap veto, no exemption).

---

## 4. Face-veto system — concrete pixel checks

**Existing (in `intelligence.py`):**
- `face_bboxes: List[Tuple[int, int, int, int]]` — (x, y, x+w, y+h) in image coords
- `tail_crosses_face()` check (existing)
- `balloon_overlaps_face()` check (existing)

**New in `src/comic/panel_script.py` (or `intelligence.py`):**

```python
def face_overlap_veto(
    balloon_rect: Tuple[int, int, int, int],
    face_bboxes: List[Tuple[int, int, int, int]],
) -> bool:
    """Return True if the balloon rect intersects any face bbox.
    AABB intersection must be > 0. No padding. Faces are sacred.
    """
    bx0, by0, bx1, by1 = balloon_rect
    for fx0, fy0, fx1, fy1 in face_bboxes:
        if not (bx1 < fx0 or bx0 > fx1 or by1 < fy0 or by0 > fy1):
            return True
    return False

def neck_overlap_penalty(
    balloon_rect: Tuple[int, int, int, int],
    face_bboxes: List[Tuple[int, int, int, int]],
    neck_pad: int = 20,
) -> int:
    """Return a soft penalty if balloon overlaps face bbox + neck pad.
    Not a hard veto (per Klein, neck is not sacred). Used in soft scoring.
    """
    # Implementation: expand face bboxes downward by neck_pad, then AABB test
    ...

def tail_crosses_face(
    tail_polyline: List[Tuple[int, int]],
    face_bboxes: List[Tuple[int, int, int, int]],
    exempt_face_index: Optional[int] = None,
) -> bool:
    """Return True if the tail polyline intersects any face bbox
    other than the exempt one (the speaker's own face).
    """
    ...
```

**Speaker's own face handling:**

- If the speaker is in the panel, their face bbox is the `exempt_face_index`
  for the tail-crosses-face check.
- The balloon body itself is NEVER exempt from the face-overlap check —
  the speaker must remain visible.
- If the only available balloon position would cover the speaker's face,
  the placer MUST veto and either widen the balloon (so it can fit
  elsewhere) or fail with PlacementError.

---

## 5. Face-veto unit tests — `tests/test_face_veto.py` (NEW)

**Coverage (from BBP §3 + Stage 2 Revised Plan §2.4):**

```python
def test_balloon_directly_over_face_vetoed():
    """Balloon placed at exact face bbox → must be vetoed."""

def test_balloon_partial_face_overlap_vetoed():
    """Balloon overlapping 50% of face → must be vetoed (any overlap = veto)."""

def test_balloon_one_pixel_face_overlap_vetoed():
    """Balloon edge touching face by 1px → must be vetoed. Faces are sacred."""

def test_balloon_adjacent_to_face_allowed():
    """Balloon within padding distance of face (no overlap) → allowed, may have soft penalty for proximity."""

def test_radio_balloon_face_veto_still_enforced():
    """Radio balloon (no tail) over face → STILL vetoed. The lack of tail doesn't bypass face protection."""

def test_speaker_own_face_exempt_from_tail_veto():
    """Normal balloon with tail pointing at speaker's own face → tail check does NOT veto (the tail is supposed to point there)."""

def test_speaker_own_face_NOT_exempt_from_body_veto():
    """Balloon body covering speaker's own face → MUST veto. Speaker must remain visible."""

def test_neck_overlap_soft_penalty_not_veto():
    """Balloon overlapping face + neck_pad (20px) → soft penalty applied, not vetoed. Neck is not sacred per Klein."""

def test_multiple_faces_each_checked():
    """Two faces in panel; balloon overlapping one → vetoed even if other face is clear."""
```

These tests run on synthetic geometry (no API calls). Fast (<1s total).
Verify a hard safety guarantee independent of AI vision.

---

## 6. Radio balloon update — italics added

**Module:** `src/comic/balloons.py` (modify existing `_draw_radio_balloon`)

**Current state:** Inline `f"{speaker.title()} via Comms: {text}"` prefix in
red, body in normal text color, double outline, no tail.

**Change:** Body text rendered in **italic** Komika Text. Inline tag stays
in red (sans italic, to make the tag visually distinct from the italic
body). Eric's decision 2026-06-02: italics yes, in addition to the tag.

**Implementation:**

```python
def _draw_radio_balloon(img, balloon, fonts, dialogue_size=24):
    """Double outline, no tail, inline red speaker tag, italic body.
    Conveys 'transmitted voice' via three signals: double outline, italic
    text, inline tag. Reader doesn't need a tail.
    """
    # ... existing layout code ...

    speaker_prefix = f"{balloon.speaker.title()} VIA COMMS:".upper()
    body_text = balloon.text  # Already-prefixed text is the body

    # Use italic font for radio body text
    body_font = fonts.dialogue_italic(dialogue_size)
    tag_font = fonts.dialogue(dialogue_size)  # Non-italic for the tag

    # Wrap using body font, but split at the tag boundary for red color
    full_text = f"{speaker_prefix} {body_text}" if balloon.speaker else body_text
    lines = wrap_text(draw, full_text.upper(), body_font, max_text_w)

    # Render each line: tag in red (non-italic), body in italic
    for ln in lines:
        if speaker_prefix and ln.startswith(speaker_prefix):
            tag_w = draw.textbbox((0, 0), speaker_prefix, font=tag_font)[2]
            draw.text((x, y), speaker_prefix, font=tag_font, fill=SPEAKER_COLOR)
            draw.text((x + tag_w, y), ln[len(speaker_prefix):],
                      font=body_font, fill=TEXT_COLOR)
        else:
            draw.text((x, y), ln, font=body_font, fill=TEXT_COLOR)
```

The wrapping is the tricky part: italic + non-italic in the same line
means the textbbox widths differ. Solution: use the wider font
(italic) for wrap-width measurement (conservative), then render with
the narrower font where appropriate (the tag is non-italic so it's
narrower, which means the actual rendering is at most slightly shorter
than the wrap assumed — safe).

**Visual result:** `WORF VIA COMMS:` in red, then italic body text in
black. Three signals for "this is a transmission": double outline, italic
body, inline tag. Reader can't miss it.

---

## 7. Recraft prompt rewrite

**Module:** `src/comic/imagegen.py` (modify `HOUSE_STYLE` + add structured
prompt builder)

**Current `HOUSE_STYLE` constant:**

```python
HOUSE_STYLE = "comic book art, bold black ink lines, flat cel-shaded coloring, 1990s Star Trek IDW comic style"
```

**New structured prompt template (per BBP §6 + Recraft V4 guide):**

```python
def build_panel_prompt(
    scene: str,                    # "TNG bridge two-shot"
    characters: List[Dict],        # [{"name": "PICARD", "position": "left", "expression": "contemplative"}, ...]
    lighting: str = "cool blue rim lighting from overhead LCARS panels, warm amber accent from aft turbolift",
    style_anchor: str = HOUSE_STYLE,
) -> str:
    """Build a Recraft V4 prompt following global-to-local structure.
    Anti-pattern: no 'negative space' or 'empty area' language.
    """
    # 1. Core concept
    char_desc = ", ".join(f"{c['name']} {c.get('position','')}".strip() for c in characters)
    parts = [f"{scene} featuring {char_desc}"]

    # 2. Background/environment (set dressing for atmosphere density)
    parts.append("TNG bridge set with visible LCARS console displays, soft blue ambient lighting, starfield on main viewscreen, console rail, conn/ops stations visible in background")

    # 3. Primary subject framing (NO negative space directives)
    parts.append("characters positioned chest-up, filling lower 50-60% of frame, leaving upper 40% for visible bridge environment and console displays")

    # 4. Physical attributes (per character)
    for c in characters:
        if c['name'] == 'PICARD':
            parts.append("Picard: bald, dignified, in red Starfleet command uniform, hands clasped behind back or at command chair")
        elif c['name'] == 'RIKER':
            parts.append("Riker: bearded, in gold Starfleet ops uniform, animated expression, gesturing")
        # etc.

    # 5. Lighting
    parts.append(lighting)

    # 6. Camera/depth/contrast
    parts.append("cinematic 16:9 composition, shallow depth of field, medium shot")

    # 7. Mood/composition
    parts.append("quiet authority, mid-scene contemplative moment")

    # 8. Style anchor + anti-text suffix
    parts.append(style_anchor)
    parts.append("NO text, NO speech balloons, NO captions, NO letters, NO words anywhere in the image")

    return ", ".join(parts)
```

**Key changes from current:**
- ❌ Remove: "negative space," "empty area for balloons," "leave room for text"
- ✅ Add: explicit composition density (characters 50-60% of frame), set
  dressing directives (LCARS, viewscreen, consoles), lighting specifics,
  mood keywords
- ✅ Structure: global-to-local order (per Recraft V4 guide)
- ✅ NO text suffix is preserved (prevents Recraft from drawing balloons)

**Per-panel overrides:** A two-shot of Picard + Riker needs different
prompt than a Picard-alone receiving comm. The structured builder takes
`characters` list — call site specifies the cast per panel.

---

## 8. Recraft prompt test matrix (Phase 1.2)

**Three prompt variants for the same Panel 2 scene (Picard + Worf comm):**

- **Variant A — current baseline:** Keep existing prompt structure with
  "negative space" language. Expected output: white void, small characters.
  Cost: ~$0.25. **Why we keep this:** baseline for the comparison.
- **Variant B — dense atmosphere, no style anchor change:** New structured
  prompt with environment/lighting directives, but same style anchor.
  Expected output: filled frame, atmospheric bridge, characters prominent.
  Cost: ~$0.25.
- **Variant C — dense atmosphere + style anchor reference:** Same as B plus
  explicit "in the style of Mike Johnson's 2009-2018 IDW Star Trek run
  with Tony Shasteen." Expected output: most on-style, but risk of
  over-fitting to a specific era.
  Cost: ~$0.25.

**Total Phase 1.2 cost: ~$0.75.** Eric reviews all three, picks direction.

**Decision recorded in:** `data/poc_comic/stage2/PROMPT_VARIANTS.md`
(simple table with prompt, output image, Eric's notes, chosen direction).

---

## 9. Orchestrator update — `scripts/render_panel_poc.py`

**Current:** Reads hardcoded dialogue, orchestrates art + vision + balloon
placer. The combadge-anchor logic is in the radio balloon path.

**New:** Accepts a `PanelScript` (or list of them for multi-panel), passes
to placer, uses new structured prompt builder.

**Key changes:**

```python
def render_panel(
    script: PanelScript,
    art_out_path: Path,
    render_out_path: Path,
    style_anchor: str = HOUSE_STYLE,
    force_regen: bool = False,
    max_attempts: int = 3,
) -> RenderResult:
    # 1. Build prompt from script
    prompt = build_panel_prompt(
        scene=script.scene,
        characters=[{"name": l.speaker, "position": ...} for l in script.lines if l.line_type == LineType.NORMAL],
    )

    # 2. Generate art (cached unless force_regen)
    art = generate_panel(art_out_path, prompt, style_anchor, aspect_ratio="16:9")

    # 3. Vision analysis
    analysis = analyze_panel(art_out_path)

    # 4. Place balloons via new reading-order placer
    try:
        placements = place_balloons_for_panel(art, analysis, script, max_attempts)
    except PlacementError as e:
        # If placement fails, retry with composition guidance addendum
        if max_attempts > 0:
            guided_prompt = prompt + " wider composition, more space between characters"
            # regen art, re-analyze, retry placement
            ...
        else:
            raise

    # 5. Render balloons onto art
    for placement, script_line in zip(placements, script.lines):
        # Construct Balloon from placement + script line
        # Draw onto art
        ...

    # 6. Save _FINAL.png and _DEBUG.png (with bbox overlays)
    return RenderResult(...)
```

**Critical: the combadge-anchor logic is GONE.** There is no
`listener_face = min(face_bboxes, ...)` line anymore. Radio balloon
position is determined by reading order, not by a pixel.

---

## 10. Three-scene test matrix (Phase 4.1-4.2)

| Scene | Difficulty | Characters | Balloons | Tests |
|-------|-----------|------------|----------|-------|
| **A: Picard alone, receiving comm** | Easy | 1 visible (Picard), 1 off-panel (Worf) | 2 (1 normal, 1 radio) | Face protection: Picard's face never covered. Reading order: Picard's balloon upper-left, Worf comm balloon below. |
| **B: Picard + Riker two-shot, dialogue + comm** | Medium | 2 visible, 1 off-panel | 3 (2 normal, 1 radio) | Face protection: both faces never covered. Reading order: Picard (left) first, Riker second, Worf comm third. Two-shot: first balloon near left character. |
| **C: Bridge wide shot, 3+ characters** | Hard | 3+ visible, multiple off-panel | 5+ (mixed) | Face protection: zero occlusions across 3+ faces. Reading order: trail through multiple balloons doesn't cross. Combadge-anchor path fully removed. |

**Each scene runs through the full pipeline:**
1. Generate art with new prompt
2. Vision analysis (Opus)
3. Place balloons via new reading-order placer
4. Render final PNG + debug overlay

**Approval gate (Phase 5):**
- [ ] All 3 scenes: zero face occlusions
- [ ] All 3 scenes: balloon reading order matches script order
- [ ] All 3 scenes: art has atmosphere (no white voids)
- [ ] All 3 scenes: text readable at ~680×500 cell size
- [ ] Radio balloons: inline tag, no tail, italic body
- [ ] Eric reviews each scene individually, signs off

**Only after all 6 checkboxes pass** do we proceed to Stage 3 (6-panel page).

---

## 11. Execution order — narrow, specific tasks

| # | Task | Output | Cost | Check-in |
|---|------|--------|------|----------|
| 1 | Add italic body to radio balloon in `balloons.py` | Modified renderer, hand-test renders OK | $0 | Show test PNG to Eric |
| 2 | Write `PanelScript` dataclass in `panel_script.py` | New module | $0 | Code review |
| 3 | Rewrite `find_balloon_position()` to take `PanelScript` and follow reading order | Modified `intelligence.py` | $0 | Unit tests pass |
| 4 | Write `tests/test_face_veto.py` with 9 tests from §5 | New test module | $0 | Tests pass |
| 5 | **Phase 1.2:** Rewrite Recraft prompt builder, generate 3 variants of Panel 2 art | `data/poc_comic/stage2/variant_A.png`, `B.png`, `C.png` | $0.75 | Eric picks direction |
| 6 | Regenerate Panel 2 + Panel 5 with chosen prompt style | `data/poc_comic/stage2/panel_2_FINAL.png`, `panel_5_FINAL.png` | $0.50 | Eric approves art |
| 7 | Run new placer on Panel 2 + Panel 5 with cached art | `*_FINAL.png` with balloons | ~$0.20 (vision) | Eric reviews |
| 8 | Run 3-scene test matrix (A, B, C) | 3 final PNGs | ~$1.75 | Eric reviews each |
| 9 | Font sizing test (3.1): render at 2K, downscale to 680×500, Eric confirms readability | `data/poc_comic/stage2/font_test_*.png` | $0 | Eric confirms |
| 10 | All pass → commit and tag v0.5.0 → proceed to Stage 3 | Git history | $0 | — |

**Total Phase 1-4 cost: ~$3.20.** Running total from project start: ~$7.80
of $70 budget.

---

## 12. What's explicitly NOT in this design

- **Stage 3 page composition** — out of scope. We get to Stage 3 only
  after Phase 5 approval gate.
- **Speech balloon shape variants** (burst, whisper, thought) — current
  NORMAL renderer handles all of these. No need to differentiate until
  the test matrix surfaces a case where shape matters.
- **LoRA-trained character consistency** — vendor pitch (BBP source [7]),
  not validated. We use Recraft's image_ref parameter if available, or
  rely on the structured prompt for now.
- **Other characters beyond Picard/Riker/Worf** — the test matrix
  exercises Picard, Riker, Worf, Sisko, Kira, etc. as needed for the
  3 scenes. Additional character prompt templates can be added
  incrementally.
- **6-panel grid page composition** — separate design pass once the
  panel-level pipeline is approved.

---

## 13. Risks and how we mitigate them

| Risk | Mitigation |
|------|------------|
| Vision model returns different face positions for same cached art | Cache vision results per art hash; flag non-determinism in debug output |
| Reading-order placer gets stuck on a panel (no valid candidates) | PlacementError → orchestrator retries with composition-guidance addendum (up to 3 attempts); final attempt surfaces to Eric |
| Italic Komika Text rendering is too narrow at 2K source | Test at 2K first; if readability fails, bump source font size |
| New prompt style still produces white voids | Test matrix with 3 variants; if all bad, iterate prompt with Eric in the loop |
| Speaker's own face bbox is wrong → balloon covers face | Face-veto tests catch this; speaker's own face is NOT exempt from body overlap |
| Mid-iteration cost overruns | Each task has a cost ceiling in the execution table; stop and check if exceeded |

---

## 14. Sign-off

This design proposal maps to:
- `data/STAGE2_REVISED_PLAN.md` Phases 1-5
- `data/COMIC_BEST_PRACTICES.md` §1-§11
- `docs/COMIC_PRODUCTION.md` broader research brief
- Eric's hard rules (Faces sacred, no zig-zag, inline tag, smaller cell
  sizes, show output, stop when told)

**To proceed I need Eric's sign-off on:**
1. The `PanelScript` data model (Section 2)
2. The reading-order placer algorithm (Section 3)
3. The face-veto test list (Section 5)
4. The radio balloon italic update (Section 6)
5. The Recraft prompt structure (Section 7)
6. The 3-scene test matrix (Section 10)
7. The execution order and cost estimate (Section 11)

**I will not write any code until you sign off.** When you do, I'll
start with Task 1 (italic body in radio balloon) — the smallest, lowest-
risk change that exercises the render path end-to-end. Show you the
output. Get your pick. Then proceed.
