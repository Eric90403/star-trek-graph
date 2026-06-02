# Stage 2 Revised Plan — Comic POC Quality Gate

**Date:** 2026-06-02
**Status:** DRAFT — pending Eric's review
**Purpose:** Replace the Opus spiral with a disciplined, testable path to
two high-quality POC panels that meet Eric's criteria. No page layout
until these panels are signed off.

---

## What went wrong with Opus's approach

Opus treated this as a geometry problem — anchor the balloon to a
combadge pixel coordinate, then search a grid for the best fit. That's
backwards. Comic balloon placement is a **script reading-order problem**
first, and a geometry constraint second. Opus also burned iterations on
balloon placement while the underlying artwork was bad (vast white
dead space, no atmosphere), and never fixed the art.

Key mistakes:
1. **Combadge as anchor** — Eric explicitly rejected this. The combadge
   is not a reliable locator. The dialogue script is.
2. **Bad art accepted** — Panels with huge white empty backgrounds were
   treated as "working" and the solution was to put balloons in the dead
   space. That's not a comic. That's a bad image with text on it.
3. **No reading-order logic** — Balloons were placed by proximity to a
   pixel coordinate, not by script sequence. In comics, the reader reads
   top-to-bottom, left-to-right. The first speaker's balloon goes
   upper-left; the reply goes lower-right or below. This is fundamental.
4. **Iterated without checking in** — Opus violated Eric's Rule 6
   repeatedly.

---

## Principles (Eric's hard rules, restated)

1. **Faces are sacred.** A balloon may cover a body but NEVER a face.
   Auto-fail on any render that covers a face pixel.
2. **No zigzag tail on radio/comm balloons.** The inline "Worf via
   Comms:" prefix conveys the signal. No tail decoration needed.
3. **Balloons close to their speakers.** Not floating in distant
   negative space.
4. **Script = reading order.** First line of dialogue = first balloon
   the reader encounters (upper-left priority). Second line = second
   balloon (below or right of first). The dialogue sequence IS the
   layout sequence.
5. **Smaller cell sizes** in practice. Text must be readable after
   downscale to in-page cell dimensions. Test at final rendered size,
   not at 2K source size.
6. **Show output between iterations. Stop when told.** No silent
   multi-hour spirals.

---

## Plan Structure

### Phase 1: Fix the Art (highest priority)

The art is the foundation. Bad art = bad comic, regardless of balloon
placement. Current Recraft output has:
- Vast white/empty backgrounds
- Characters small in the frame
- No atmosphere (bridge should have blue ambient light, console glow,
  starfield on viewscreen — not a white void)

**Task 1.1: Improve Recraft prompts for composition density**

The current prompts ask for "negative space" and "empty area for
balloons." This tells the model to leave the panel mostly empty.
Rewrite prompts to:
- Fill the frame with atmosphere and environment detail
- Position characters prominently (occupying 40-60% of frame height)
- Include specific lighting cues ("soft blue rim lighting from
  overhead console panels, warm amber from aft turbolift")
- Include set dressing ("blinking LCARS displays, railings, conn/ops
  stations visible in background")
- Remove ALL "negative space" / "empty area" language from prompts

Balloons go OVER the art. The art should be worth looking at on its own.

**Task 1.2: Evaluate art quality with a test matrix**

Generate 3 variants of the same panel (Picard in command chair) with
different prompt strategies:
- A: Current prompt (baseline — expect white void)
- B: Dense-atmosphere prompt (no negative-space language)
- C: Dense-atmosphere + reference to a specific IDW issue style

Eric reviews all three and picks direction. Cost: ~$0.75 (3 images at
$0.25 each).

**Task 1.3: Fix the two-shot composition (Panel 5)**

The two-shot is the hardest panel. Current output has two small figures
floating in white space. A proper TNG bridge two-shot should show:
- Two characters from chest-up, FILLING the lower 50-60% of frame
- Bridge environment visible around and behind them
- Console rail, viewscreen glow, or turbolift frame as compositional
  anchor
- Characters positioned left/right with a gap between them (where
  dialogue balloons can sit, centered between speakers)

**Deliverable:** Two regenerated panel artworks (Panel 2 + Panel 5)
that Eric approves BEFORE any balloon work proceeds.

---

### Phase 2: Script-Driven Balloon Layout

The dialogue script determines balloon order, not pixel coordinates.

**Task 2.1: Define a PanelScript data structure**

Replace the current balloon spec (which is just a list of balloon dicts
with no order semantics) with an explicit script:

```
PanelScript:
  scene: "Bridge - Night"
  lines:
    - order: 1
      speaker: RIKER
      text: "Two centuries. That's a long time to wait for rescue."
      type: NORMAL
      off_panel: false
    - order: 2
      speaker: WORF
      text: "Or a long time for a trap to remain set."
      type: RADIO
      off_panel: true
```

The `order` field IS the reading order. The placer must respect it.

**Task 2.2: Implement reading-order balloon placement**

Current `find_balloon_position()` scores candidates by distance to
speaker anchor. Replace/augment with reading-order constraints:

- Line 1 balloon: placed in the upper-left region of the panel
  (or upper-center for a single-balloon panel)
- Line 2 balloon: placed below and/or right of Line 1
- For two speakers in a two-shot: Line 1 balloon near speaker 1
  (left character), Line 2 balloon near speaker 2 or below Line 1
- For a radio/comm line: the balloon is NOT anchored to a combadge.
  It is anchored to the script context — who is receiving the call
  (Picard), and it goes in the reading-order position AFTER the prior
  balloon. If Riker speaks first (left, upper), Worf's comm follows
  (could be right and slightly lower, or left-below).

The key insight: in published comics, when a comm call interrupts a
conversation, the comm balloon typically appears ABOVE or BETWEEN the
in-room speakers, not pinned to a chest pixel. The reader understands
"this is a comm call" from the double-outline and the "via Comms"
prefix — NOT from where the tail points.

**Task 2.3: Remove combadge-as-anchor entirely**

Delete the combadge proximity logic from the radio balloon anchor
path in `render_panel_poc.py`. Replace with:
- If `off_panel=true` and `type=RADIO`: anchor at the LISTENER's face
  center (for tail direction) OR no anchor at all (no tail on radio
  balloons per Eric's Rule 2). The double-outline + inline speaker
  tag conveys "this is a transmission."
- Actually: since Rule 2 says NO zigzag tail, and radio balloons have
  no tail, the anchor concept for radio balloons is purely about
  WHICH REGION the balloon occupies. That's a reading-order /
  layout decision, not a geometry-to-combadge decision.

**Task 2.4: Face-protection hard veto (verify it works)**

The existing `find_balloon_position()` already has face-overlap and
tail-crosses-face vetoes. Verify these are actually enforced:
- Write a unit test that places a balloon directly over a known face
  bbox and confirms it's vetoed
- Write a test that places a balloon adjacent to a face (within
  padding) and confirms it's allowed
- Check that radio balloons (no tail) don't accidentally bypass the
  face-veto because they skip tail-crossing checks

---

### Phase 3: Text Sizing and Readability at In-Page Scale

**Task 3.1: Measure text readability at target cell size**

A full comic page at 1400px wide with a 6-panel grid means each cell is
roughly 680×500px (2×3 grid with gutters). Source art is 2688×1536, so
a cell renders at ~25% of source size.

Current font: 56pt at 2K source. At 25% that's ~14pt effective —
borderline readable. Test:
- Render a panel at 2K with 56pt text
- Downscale to 680×500
- Check if text is legible (human review, not automated)
- If not, increase source font size or reduce word count per balloon

**Task 3.2: Establish font-size floors**

Define minimum font sizes that remain readable at in-page cell
dimensions. Document these as constants. Likely:
- Dialogue: 56pt at 2K (current) → may need 64-72pt
- Comm prefix: 48pt at 2K → may need 56pt
- Caption: 48pt at 2K → may need 56pt

These become hard constraints, not tuning knobs.

---

### Phase 4: Multi-Scene Consistency Test

Don't validate on one panel and declare victory. Test across different
scene types.

**Task 4.1: Select 3 test scenes of increasing difficulty**

| Scene | Difficulty | Why |
|-------|-----------|-----|
| A: Picard alone on bridge, receiving comm | Easy | One face, one balloon, no overlap risk |
| B: Picard + Riker two-shot, dialogue + comm | Medium | Two faces, reading order, balloon proximity |
| C: Bridge wide shot, 3+ characters | Hard | Multiple faces, multiple balloons, dense layout |

**Task 4.2: Run all 3 scenes through the pipeline**

Generate art → vision analysis → script-driven balloon placement →
render. Compare results across scenes for:
- Face protection (zero face occlusions across all 3)
- Reading order (balloon sequence matches script sequence)
- Art quality (no white void, proper atmosphere)
- Text readability at cell scale

**Task 4.3: Regression guard**

Save the vision analysis JSON for each scene. On future runs, if the
vision model returns different face positions for the same cached art,
flag it (vision is non-deterministic). This prevents "works on my
machine" failures.

---

### Phase 5: Approval Gate

Before any page composition work:

- [ ] All 3 test scenes render without face occlusion
- [ ] Reading order matches script order on all 3
- [ ] Art has atmosphere (no white voids) on all 3
- [ ] Text readable at ~680×500 cell size on all 3
- [ ] Radio/comm balloons use inline prefix, no zigzag tail, no
      combadge anchor
- [ ] Eric has reviewed and approved each scene individually

Only after ALL checkboxes pass do we proceed to Stage 3 (6-panel page
composition).

---

## Cost Estimate

| Phase | API Calls | Est. Cost |
|-------|----------|-----------|
| 1.2 Art test matrix (3 variants × 1 panel) | 3 Recraft images | $0.75 |
| 1.3 Regenerate Panel 2 + Panel 5 | 2 Recraft images | $0.50 |
| 2.2-2.4 Placement (cached art, vision only) | ~6 Opus calls | $1.20 |
| 3.1 Font sizing tests | 0 (local render) | $0.00 |
| 4.2 Three scenes (art + vision + render) | 3 Recraft + 3 Opus | $1.75 |
| **Total** | | **~$4.20** |

Running total from project start: ~$8.80 of $70 budget.

---

## What Gets Committed (and when)

Nothing is committed now (Eric's call — the work isn't trusted yet).

After Phase 1 (art approved):
  - `src/comic/imagegen.py` (with improved prompt template)
  - The approved art assets in `data/poc_comic/stage2/`

After Phase 4 (all scenes pass):
  - `src/comic/intelligence.py` (with script-driven placement)
  - `scripts/render_panel_poc.py` (with PanelScript + reading order)
  - `src/comic/balloons.py` (radio balloon: no tail, inline prefix)
  - All test scene outputs
  - This plan document (updated with results)
  - `docs/HANDOFF_2026-06-02_Stage2.md` (updated or replaced)

The deleted `SAMPLE_TNG_The_Last_Voice_of_Kethani_PAGE_1.png` from
v0.4.0 gets restored before any commit (per handoff doc).

---

## Execution Order (narrow, specific tasks)

1. Rewrite Recraft prompts: remove "negative space" language, add
   atmosphere/composition density directives → generate 3 test
   variants of Panel 2 → Eric reviews
2. Eric picks art direction → regenerate Panel 2 + Panel 5 with
   chosen prompt style → Eric approves art
3. Implement PanelScript dataclass + reading-order placement logic in
   `intelligence.py` → remove combadge anchor code → add face-veto
   unit tests
4. Run all 3 test scenes (A/B/C) → Eric reviews each
5. Font sizing: render at 2K, downscale to 680×500 → Eric confirms
   readability → adjust if needed
6. All pass → commit → proceed to Stage 3 (page layout)

Between each task: show output, get Eric's go-ahead. No silent
iteration.
