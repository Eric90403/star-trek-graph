# ⚠️ DEPRECATED — DO NOT FOLLOW ⚠️

**Superseded by:** `data/STAGE2_REVISED_PLAN.md` (2026-06-02)

This document describes the broken Opus-iteration approach that led to a
silent multi-hour spiral. Its core recommendation ("fix the one anchor bug,
then move to Stage 3") was rejected. The revised plan calls for:

1. Fix the art first (rewrite Recraft prompts — kill "negative space"
   language, add atmosphere/LCARS density directives).
2. Redesign balloon placement around script reading order, not pixel
   proximity to a combadge.
3. Delete the combadge-as-anchor branch entirely.
4. Establish face-veto unit tests as a hard safety guarantee.
5. Test across 3 scenes (A: easy / B: medium / C: hard) before any
   page composition.

The original content is preserved below for historical reference only.

---

# Handoff — Stage 2 Comic Pipeline (in-progress, uncommitted)

**Date:** 2026-06-02
**Last shipped commit:** `00c1659` v0.4.0 — comic POC merged in PR #1
**Repo:** https://github.com/Eric90403/star-trek-graph

This document captures everything since v0.4.0 so a fresh session can pick
up cleanly. Nothing in this work has been committed; the working tree has
uncommitted changes from a long iteration spiral.

---

## Active goal (Eric's directive)

Build a publishable Stage 3 (full Page 1 of "The Last Voice of Kethani")
using the comic platform.

Eric's hard requirements:
1. **Faces are sacred.** A balloon may cover a body but NEVER a face. Auto-fail.
2. **Comm balloons** show inline speaker prefix: `"Worf via Comms: {text}"`
3. **No zigzag tail** on radio/comm balloons — the inline tag conveys the signal
4. **Balloons close to their speakers** — not floating in distant negative space
5. **Smaller cell sizes** in practice (multiple panels per page → balloon text
   must be sized so it remains readable after downscale to in-page cell size)
6. **Show output between iterations.** Stop when the user says stop. Do not
   keep tweaking without explicit go-ahead. (This rule was violated repeatedly
   in this session — apologize, don't repeat.)

---

## Stage plan (where we are)

- ✅ Stage 1 — 10 style samples generated, Eric picked **#01 IDW Modern**
- 🟡 Stage 2 — single-panel POC for Panel 2 + Panel 5 — works on art, balloon
  placement still drifting. **Currently stuck here.**
- ⬜ Stage 3 — full 6-panel Page 1 (not started)

---

## What's working

| Component | Status |
|---|---|
| Recraft V4.1 Pro via OpenRouter (`recraft/recraft-v4.1-pro`) | ✅ $0.25/image at 2K, with `image_config.aspect_ratio: "16:9"` |
| IDW house-style prompt template (`HOUSE_STYLE` constant) | ✅ delivers genuine TNG-comic likenesses for Picard / Riker |
| No-text prompt suffix (prevents Recraft drawing its own balloons) | ✅ |
| WebP→PNG transcoding (Recraft returns WebP in .png-named files) | ✅ |
| Vision analysis via Claude Opus on OpenRouter | ✅ accurate face bboxes |
| Vision returns: faces, bodies, combadges, preexisting balloons, empty regions | ✅ |
| "Worf via Comms:" inline red prefix in radio balloon | ✅ |
| Zigzag tail removed from radio balloons | ✅ |
| Komika Text body font, Bangers display, ALL CAPS | ✅ |
| Font scaling: dialogue at 56pt at 2K source (~22pt at downscaled comic size) | ✅ |
| Hard-veto placer: face overlap, panel edge margin, prior balloon overlap | ✅ |
| Tail-crosses-face veto exempts the SPEAKER's own face | ✅ |
| Width retry loop (narrowest first, pick best score) | ✅ |
| Coordinate scaling: vision 1456×816 space → image 2688×1536 space | ✅ |

---

## What's NOT working (live bug)

**Balloon placement still drifts AWAY from the intended speaker** on the two-shot
panel (Panel 5).

Observed in `data/poc_comic/stage2/panel_5_picard_riker_twoshot_FINAL.png`:
- Both balloons (Riker's normal speech + Worf-via-comms) end up clustered on
  the right side near Riker
- The Worf comm balloon SHOULD anchor near Picard (the listener / combadge
  receiver), not Riker
- The placer logs show `anchor=(2344, 1204)` for the Worf balloon, but Picard's
  scaled face center is `(427, 912)` and Riker's is `(2085, 925)` — anchor
  (2344, 1204) is to the right of Riker, matching neither face

The `listener_face = min(analysis.face_bboxes, key=lambda f: f[0])` line in
`scripts/render_panel_poc.py` should be selecting Picard's face (leftmost x).
This was the **last unverified bug** when Eric called stop.

**Likely root cause to investigate:** the coord-scaling block mutates
`analysis.face_bboxes` after `analysis_summary` already printed the unscaled
boxes. The list of tuples is replaced cleanly (not mutated in place). The
debug print line `balloon 2 WORF: anchor=(2344, 1204)` was added but the
intermediate `listener_face` and `cb_x_target` values are not yet logged —
so we don't actually know whether `listener_face` is Picard or Riker at
print time.

---

## Working tree (uncommitted)

```
D  data/poc_comic/SAMPLE_TNG_The_Last_Voice_of_Kethani_PAGE_1.png   (removed)
 M src/comic/balloons.py                                            (modified)
?? data/comic_styles/                                               (new — 10 style samples + contact sheet)
?? data/poc_comic/stage2/                                           (new — Panel 2 & 5 art + finals + debug overlays)
?? scripts/render_panel_poc.py                                      (new — Stage 2 orchestrator)
?? src/comic/imagegen.py                                            (new — Recraft V4.1 Pro client)
?? src/comic/intelligence.py                                        (new — vision + balloon placer)
```

### File summaries

#### `src/comic/imagegen.py` (NEW, ~110 lines)
- `generate_panel(out_path, prompt, style_anchor, aspect_ratio="16:9", reference_image=None)`
- Uses OpenRouter `recraft/recraft-v4.1-pro` at `chat/completions` with `modalities: ["image"]`
- Injects a NO_TEXT clause so Recraft doesn't draw its own balloons
- WebP→PNG transcoding on save
- Loads key from `~/.hermes/.env` or `OPENROUTER_API_KEY` env var
- `HOUSE_STYLE` constant locked to IDW Modern (Stage 1 selection)

#### `src/comic/intelligence.py` (NEW, ~430 lines)
- `analyze_panel(image_path, model="anthropic/claude-opus-4.5")` — vision call returning `PanelAnalysis` dataclass:
  - `face_bboxes`, `body_bboxes`, `combadges`, `preexisting_bboxes`, `empty_regions`
- `find_balloon_position(...)` — searches grid + speaker-adjacent + empty-region centers, scores each:
  - Hard vetoes: panel edge, face overlap, tail-crosses-other-face, prior balloons, pre-existing text/balloons
  - Soft scoring: distance-to-speaker dominant (up to +300), empty-region bonus (+10/+25/+50 by quality), reading order, body-overlap penalty
  - Speaker's own face exempt from tail-crossing veto
- Debug print of top 5 candidates per call

#### `src/comic/balloons.py` (MODIFIED)
Changes from the merged v0.4.0:
- `OUTLINE_W` 3→5 (for 2K canvas)
- `CORNER_RADIUS` 28→36, `PADDING_X` 18→28, `PADDING_Y` 14→22 (scale with bigger font)
- Radio balloon: text prefix is now `f"{speaker.title()} via Comms: {text}"` (was `"SPEAKER: text"`)
- Radio balloon: prefix renders in red `SPEAKER_COLOR`
- Radio balloon: **zigzag tail call removed entirely**
- Radio balloon: text wrap width 380 → 700
- Normal balloon: text wrap width 380 → 700
- Caption: text wrap width 480 → 800

#### `scripts/render_panel_poc.py` (NEW, ~340 lines)
Stage 2 orchestrator. Renders Panel 2 (Picard + Worf comm) and Panel 5
(Picard/Riker two-shot + Worf comm) end-to-end:
1. `generate_panel()` with caching via FORCE_REGEN flag
2. `analyze_panel()` → coord-scale vision response to actual image dims
3. Per balloon: compute anchor (radio off-panel → listener face/combadge; normal → speaker face)
4. Width retry loop: try narrowest → widest, pick highest scoring placement
5. Up to 3 attempts with composition-guidance addendum if all balloons can't place
6. Save `_FINAL.png` + `_DEBUG.png` with bbox overlays

The current bug almost certainly lives in the **anchor computation for the
radio balloon path** — the `listener_face` selection is producing an anchor
position no face center matches.

---

## OpenRouter spend this session

- Diagnostic (figuring out `modalities` parameter): $0.61
- 10 style samples at V4.1 (Stage 1): $0.40
- Various Stage 2 generations + Opus vision passes: ~$3.60
- **Total: ~$4.60 of $70 available**

Balance remaining: ~$65 (verify with `curl https://openrouter.ai/api/v1/credits`).

---

## Decisions to remember

1. **House style locked:** IDW Modern. Style anchor in `imagegen.HOUSE_STYLE`.
2. **Resolution:** Generate at 2K (1456×816 returned), font at 56pt.
3. **Aspect:** 16:9 for landscape panels (Recraft's `image_config.aspect_ratio`).
4. **Vision model:** Opus, not Sonnet. Sonnet hallucinated face positions.
5. **Comm balloon style:** No tail. Inline "Worf via Comms:" prefix in red. Double outline.
6. **Auth:** OpenRouter key reads from `~/.hermes/.env`. No project-specific key needed.
7. **PR workflow:** Branch protection on `main` — all contributor work via PRs; owner has bypass for solo housekeeping.

---

## Where a fresh session should start

1. **Read this file first.** Then `docs/COMIC_PRODUCTION.md` (the research brief that drives the comic design).
2. **Inspect the broken output:** `data/poc_comic/stage2/panel_5_picard_riker_twoshot_FINAL.png` — both balloons clustered right of Riker; the Worf-comms balloon should be near Picard.
3. **Read** `scripts/render_panel_poc.py` around lines 200-235 (the anchor-computation block for radio off-panel balloons).
4. **Hypothesis to verify:** Add a print like `print(f"  listener_face={listener_face} cb_x_target={cb_x_target}")` right before the `anchor =` assignment in the radio branch. Run with `FORCE_REGEN=False` (cached art, ~$0.20 in Opus only). Confirm whether `listener_face` is actually Picard or something unexpected.
5. **Once that one bug is understood:** show Eric the corrected Panel 5, get sign-off, THEN proceed to Stage 3 (full 6-panel page).
6. **Don't iterate more than 2-3 times without checking in with Eric.** This was the failure mode in this session.

---

## What got committed in v0.4.0 (already on main, do not redo)

- `src/comic/balloons.py` (initial version)
- `src/comic/panels.py` (post-processing chain)
- `src/comic/page.py` (page composer)
- `docs/COMIC_PRODUCTION.md` (15KB research brief)
- `assets/fonts/` (Komika Text + Bangers)
- `data/poc_comic/SAMPLE_TNG_The_Last_Voice_of_Kethani_PAGE_1.png` (the v0.4.0 sample — note this file is currently DELETED in the working tree; should be restored before next commit)

---

## How to resume cleanly

```bash
cd ~/projects/star-trek-graph
git status   # see the diff documented above
git stash    # OR: keep working tree as-is and continue with this file as the map

# To reset to the last clean commit and start over:
git checkout data/poc_comic/SAMPLE_TNG_The_Last_Voice_of_Kethani_PAGE_1.png
git checkout src/comic/balloons.py
# Then delete the untracked new files if desired

# To continue from where we stopped:
.venv/bin/python scripts/render_panel_poc.py   # re-renders both panels using cached art
```

The full session transcript should be available via `session_search` — search
for "comic platform" or "Recraft" or "Stage 2" to find context.
