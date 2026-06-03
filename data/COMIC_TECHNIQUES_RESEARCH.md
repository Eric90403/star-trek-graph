# Comic Balloon Tail + Placement — Technique Research

**Date:** 2026-06-02
**Trigger:** Visual audit of Panel 2 and Panel 5 in v0.4.1 work-in-progress
revealed (a) the smooth tapered tail rendered as two diverging strokes
that never converge, and (b) the multi-balloon placement put line-2's
balloon over the wrong speaker. Both were homegrown implementations
without prior research. This document collects what other people have
done so we can replace invention with evidence.

**Method:** Three parallel research subagents tasked with narrow,
sourced research questions. Each handed back a markdown report. This
document is the synthesis + action plan.

**Status:** RESEARCH COMPLETE — supersedes the placer scoring in
`src/comic/intelligence.py::place_balloons_for_panel` and the tail
construction in `src/comic/balloons.py::_draw_smooth_tail`.

---

## 1. The two failures, named

| Failure | What we built | What's wrong | Evidence |
|---|---|---|---|
| **Tail two-stroke divergence** | `_draw_smooth_tail` strokes two Bezier curves as separate paths, fills a polygon between them | Stroking the two curves as open paths shows their individual outlines on BOTH sides. Industry pattern is a single closed Bezier path, UNIONED with the balloon, then stroked once. | Comical-JS `arcTail.ts` (BloomBooks/comical-js, MIT) — explicit fix: `addSegments` to merge into one path, then `uniteBubbleShapes()` boolean union [Sub1, Sub2] |
| **Horizontal bands by line index** | `_reading_order_zone` puts line 1 in top band, line 2 in middle band, line N in bottom band, then biases candidates by zone | **No production source uses this.** All four academic papers and all four letterer references use *speaker-anchored* placement with reading-order as a CONSTRAINT, not a layout axis. The "horizontal bands" approach explains why line-2 lands over the wrong speaker. | Eddie Campbell's Rule #3 directly diagnoses the failure: "a reader will read a balloon and then read the next nearest balloon" — if line-2's balloon is nearest the wrong speaker, the reader mis-assigns it [Sub3] |

---

## 2. Tail construction — the canonical technique

**Single closed Bezier path, unioned with the balloon body.**

### 2.1 The construction (from Comical-JS arcTail.ts)

```
Inputs:
  - balloon_outline_path  (the rounded-rect or oval)
  - root_xy               (a point inside the balloon, near the speaker-side edge)
  - tip_xy                (the target — typically 50-60% of the way from
                           balloon-edge to speaker's head/mouth)

Step 1: Find the base intersection.
  Build a temporary cubic Bezier from root → mid → tip.
  Intersect that Bezier with the balloon_outline_path.
  The intersection point is base_of_tail (one point on the outline).

Step 2: Build the two base anchors straddling that point.
  Walk ±baseAlongPathLength/2 (default 20 units) ALONG the balloon outline
  from base_of_tail, in both directions. These are `begin` and `end`.
  Then nudge each 1 unit inward (toward root) to hide the bubble border
  edge under the tail.

Step 3: Build the two side Beziers.
  side1 = Bezier(begin, mid1, tip + deltaTip)
  side2 = Bezier(tip - deltaTip, mid2, end)
  Where mid1, mid2 are perpendicular to the (base_of_tail → tip) line,
  with widths derived from midPointWidth (default ~5-6 units).
  deltaTip = deltaMid/1000 — a SUB-PIXEL offset so the tip has nonzero
  width. (Workaround for Chrome rendering glitches with mathematically
  zero-width strokes.)

Step 4: Merge the two side Beziers into ONE closed path.
  path = side1
  path.addSegments(side2.segments)  // single closed path, NOT two open ones

Step 5: Union with the balloon outline.
  final_silhouette = path.unite(balloon_outline_path)

Step 6: Stroke + fill final_silhouette as a single shape.
  Renders as one continuous outline around balloon + tail.
```

Source: Comical-JS `src/arcTail.ts`, lines `makeShapes()` function.
https://github.com/BloomBooks/comical-js/blob/master/src/arcTail.ts [Sub1, Sub2]

### 2.2 Why our current implementation fails

Our `_draw_smooth_tail`:

```python
left  = _quadratic_bezier(bp1, (ctrl_x, ctrl_y), (tip_x, tip_y), steps=14)
right = _quadratic_bezier(bp2, (ctrl_x, ctrl_y), (tip_x, tip_y), steps=14)
polygon = left + list(reversed(right))
draw.polygon(polygon, fill=BALLOON_FILL)
for curve in (left, right):
    for i in range(len(curve) - 1):
        draw.line([curve[i], curve[i + 1]],
                   fill=BALLOON_OUTLINE, width=OUTLINE_W)
```

The polygon is filled correctly (white between the curves). But the
two outline strokes are drawn as **separate open curves**, each with
the full OUTLINE_W (5 px) thickness. The outlines extend off the
polygon edge on BOTH sides at the tip, where the polygon comes to a
point but the strokes don't. Result: two diverging lines that don't
appear to converge.

The fix is structural, not parametric: build a single closed path,
fill+stroke it as one shape, OR boolean-union with the balloon.

### 2.3 Tip termination

- Blambot: "Tail should terminate at **50-60% of the distance** between
  balloon and character's head." [Sub1: blambot.com]
- Balloon Tales (Comicraft): "click at about 1/3 to 1/2 the distance
  to the character's mouth." [Sub1]
- Treat **40-60% of (balloon-edge → mouth)** as the industry-acceptable
  range. The reference line is balloon edge → mouth, NOT balloon edge
  → face center.

**For our code:** the anchor point we pass should be the speaker's
mouth or the face-bottom edge, NOT the face center. Our current code
uses face center, which is why Panel 5's tail tip ended up inside
Picard's eye area.

### 2.4 Common bugs to avoid

1. **Two diverging strokes** (our bug) — fix per §2.1.
2. **Tip overshoot at zero width** — renderers can draw stroke pixels
   past a mathematically-zero tip. Comical-JS uses a deltaTip =
   deltaMid/1000 sub-pixel offset to dodge this. [Sub1]
3. **Visible bubble border under tail base** — if begin/end sit exactly
   on the bubble outline, the bubble's stroke shows through the union.
   Comical-JS nudges each base point 1 unit inward. [Sub1]
4. **Tail pointing at hand/leg/shoulder** — Blambot and Balloon Tales
   both warn: tail must point at the mouth, never at a body part. The
   anchor must be a face/mouth point. [Sub1]
5. **Tails crossing each other** — universal "looks rather silly" rule
   (Klein, Staley). [Sub3]

### 2.5 PIL constraint

PIL has **no native cubic Bezier fill**. Three options:
- (a) Flatten the Bezier curves to ~100-segment polylines, then
  `ImageDraw.polygon()`. Simplest, works at our 2K resolution.
- (b) Use `aggdraw` (PIL-compatible) for true antialiased Bezier fill.
- (c) Use `skia-python` or `cairocffi` for a real vector backend.

Recommendation: **(a) first** — flatten to polylines, call polygon
once with fill, then call line-loop once for stroke. Matches the
Comical-JS algorithm with minimum dependency change.

---

## 3. Placement — the canonical technique

**Speaker-anchored, with reading-order as a constraint.**

### 3.1 The convergence across sources

All four academic papers I checked plus all four letterer references
agree on one core principle:

> Balloon position is determined by the SPEAKER's position. Reading
> order is then satisfied by composition choices (panel layout,
> speaker arrangement, occasionally flopping the panel), NOT by
> forcing balloons into horizontal bands by script order.

Eddie Campbell's "Rule #3" (with Dave Gibbons agreeing) is the
diagnostic for our bug:

> "A reader will read a balloon and then read the next nearest balloon
> even if they haven't already read all the ones in the current panel."
> — Campbell, eddiecampbell.blogspot.com [Sub3]

In Panel 5, line-2 (Riker) ended up in a horizontal band that placed
its balloon closer to Picard's body than Riker's. By Rule #3, the
reader assigns that balloon to Picard. The "horizontal bands by line
index" axis caused the misattribution.

Klein's primary rule:

> "Within a panel it's always best if the character on the left speaks
> first." — Todd Klein, kleinletters.com [Sub3]

**When this holds, speaker-anchored placement = reading-order placement
for free.** When it doesn't (forced by script), letterers either edit,
flop the panel, split panels, or accept some awkwardness.

### 3.2 The algorithm to implement

For each line in script order (1, 2, 3, ...):

```
1. Identify the speaker's anchor point.
   - NORMAL: speaker's mouth or face-bottom (NOT face center).
   - RADIO (off-panel): anchor = nearest panel edge. The radio
     balloon "butts against the panel border" per Blambot. [Sub3]

2. Build candidate positions around the speaker:
   - Klein: "Balloons look best ABOVE and AWAY from the speaker."
   - For an on-panel speaker: candidates form a fan above the speaker's
     head, biased toward the panel edge nearest the speaker.
   - For a RIGHT-side speaker: bias candidates to the upper-right.
   - For a LEFT-side speaker: bias candidates to the upper-left.
   - For an off-panel speaker (radio): candidates along the nearest
     panel edge.

3. Apply hard vetoes:
   - Panel containment + edge margin.
   - Face overlap (zero pixels — faces are sacred).
   - Prior-balloon overlap (with gutter padding).
   - Tail crosses non-speaker face.
   - Tail crosses other balloon's tail.

4. Score surviving candidates:
   - PRIMARY: distance to speaker's anchor (closer is better, capped
     so balloon doesn't hug the face).
   - SECONDARY: reading-order CONSTRAINT — line N's balloon must be
     readable AFTER line N-1's. Check: from line N-1's balloon
     position, is line N's balloon to the right OR below? If neither,
     veto (or heavy penalty).
   - TERTIARY: empty region bonus (place over starfield, not over
     console detail).
   - PENALTY: body overlap (light), neck overlap (medium).

5. Eddie Campbell test (the diagnostic we owe ourselves):
   - After placing a candidate, check: is this balloon nearer to any
     OTHER face than to the intended speaker's face? If yes, the
     reader will mis-assign it. Veto.

6. Width-retry: if no candidate survives, narrow the balloon and retry.
   If all widths fail, raise PlacementError. Do NOT add a full-panel
   fallback grid.
```

### 3.3 Off-panel radio balloon specifics

Documented (Blambot):
- Off-panel tail butts the panel border.
- Radio balloons inherit off-panel conventions when the transmitter
  is not visible.

Convention (from Sub3, with caveat that no IDW-specific source was
found):
- When the radio line is the LAST line and no on-panel character is
  shown listening: position at bottom or bottom-right of the panel
  (last in Western reading order), tail/edge touching the panel border.
- When a specific on-panel character is clearly receiving the call:
  place ABOVE that character with tail butting the panel edge near
  them, visually linking transmission → receiver.

For our code: the placer treats radio balloons as having `speaker_anchor
= nearest_panel_edge_point_to_listener` (or just `nearest_panel_edge`
when no listener), and the existing rule "no tail on radio" still holds
(we use inline `Speaker via Comms:` prefix instead).

### 3.4 Academic optimization formulations (for reference, not implementation)

For future reference if heuristic falls short:

- **Chun et al. 2006**: cartographical labeling (same family as map
  city-label placement). Score candidates by distance-to-speaker +
  ROI occlusion + panel-boundary penalty. [Sub3]
- **Chu & Yu 2013**: Particle Swarm Optimization over intra-panel +
  inter-panel cost. ACM IMMPD. [Sub3]
- **Yang et al. 2021**: face detection + lip-motion identifies speaker;
  layout algorithm keeps reading order and avoids face occlusion.
  ACM TOMM 17(2). [Sub3]

We don't need PSO. The speaker-anchored heuristic + Eddie Campbell
test handles our case. Mention only because if the heuristic fails on
some future scene (e.g. 5+ speakers, dense panel), PSO is the
documented next step.

---

## 4. What this changes in our code

### 4.1 `balloons.py::_draw_smooth_tail` — rewrite

Replace the two-stroke construction with a single closed-path
construction:

1. Compute base intersection on balloon outline.
2. Walk ±baseAlongPathLength/2 along the outline for `begin`, `end`.
3. Compute side Beziers sharing a mid control point.
4. Flatten side1 + reversed(side2) into a single polyline.
5. Append the balloon outline arc between `begin` and `end` to close
   the path with the balloon body. OR draw tail polygon then balloon
   outline AFTER, so the balloon's own stroke covers the tail's seam
   at base.
6. Use sub-pixel deltaTip offset to avoid zero-width tip artifacts.

Implementation: pure Python, PIL polylines (no aggdraw needed if we
flatten at ~30+ segments).

### 4.2 `intelligence.py::place_balloons_for_panel` — rework

Replace `_reading_order_zone` (horizontal bands) with
`_speaker_zone_candidates`:

- For each line, candidates form a fan above/around the speaker's
  anchor point (head-top or face-top edge, not face center).
- Off-panel radio: candidates along the nearest panel edge.
- Reading-order is a CONSTRAINT checker, not a candidate generator:
  reject candidates whose center is upper-left of the prior balloon
  (i.e. would be read before it).
- Add Eddie Campbell test: after placement, verify nearest-face
  assignment matches intended speaker.

### 4.3 `panel_script.py` — extend with anchor-type hint

Add an optional `anchor_hint: Literal["mouth", "face_top", "panel_edge"]`
field to ScriptLine, so callers can specify how to anchor radio vs.
normal lines without the placer having to infer. Default: "mouth" for
NORMAL, "panel_edge" for RADIO.

### 4.4 New tests required

- `tests/test_tail_geometry.py`: visual regression on the new tail
  construction. Render 8 tails at varying angles + distances,
  hash-compare to a committed baseline OR assert the tail polygon
  is closed (start == end) and the outline is one continuous path.
- `tests/test_eddie_campbell_test.py`: synthetic panels where the
  naive placer puts line-2 closer to the wrong speaker, assert the
  new placer either repositions or vetoes.
- Existing 31 tests still pass — the speaker-anchored approach is a
  superset of what they check.

---

## 5. Open questions for Eric

1. **PIL vs. skia-python**: Going with PIL polyline-flatten approach
   (no new deps). Confirm? Alternative is to add `aggdraw` (PIL-compatible,
   adds true antialiased Bezier) or switch to `skia-python` (best
   quality, ~80MB dep). My recommendation: PIL flatten, ship the
   tail rewrite, evaluate quality, only switch backend if needed.

2. **Anchor hint default**: Should normal-balloon anchor default to
   `"mouth"` (preferred per Blambot but vision API gives face bboxes
   not mouth points, so we'd compute mouth ≈ face_bottom) or `"face_top"`
   (closer to where the balloon should be approaching from)? My
   recommendation: `"face_top"` because the BALLOON is above the
   speaker; the tail goes DOWN to the mouth, so an anchor at face-top
   is approximately right and avoids the face-center-into-eye bug.

3. **Eddie Campbell test as veto or score**: When line-2's balloon is
   visually closer to another speaker than the intended one — should
   this be a hard VETO (raise PlacementError if no fix found) or a
   STRONG PENALTY (try harder but eventually accept)? My recommendation:
   strong penalty (~-200 score) initially, escalate to veto if visual
   audits still show misattribution.

4. **Radio balloon listener-anchor**: Per Sub3 convention,
   "when a specific on-panel character is clearly receiving the call,
   place ABOVE that character." But this is exactly what we tried in
   the spiral and rejected. Reconciliation: position above the listener
   IS correct convention, BUT the inline `Speaker via Comms:` prefix
   removes the dependency on visual proximity for speaker identification.
   So we CAN bias toward listener for radio placement now without
   reintroducing the misattribution bug. Confirm this is OK before
   I write code that does it.

---

## 6. Sources

### Subagent 1 (Tail rendering technique)
- Balloon Tales (Comicraft), "Creating Tails and Joins" —
  https://balloontales.com/creating-tails-and-joins/
- Blambot, "Comic Book Grammar & Tradition" —
  https://blambot.com/pages/comic-book-grammar-tradition
- BloomBooks/comical-js, `src/arcTail.ts` and `src/tail.ts` —
  https://github.com/BloomBooks/comical-js/blob/master/src/arcTail.ts

### Subagent 2 (Open-source implementations)
- BloomBooks/comical-js (TypeScript, MIT, gold standard) —
  https://github.com/BloomBooks/comical-js
- rogudator/rogudators_speech_bubble_generator (Python, GPL-3.0) —
  https://github.com/rogudator/rogudators_speech_bubble_generator
- iopred/comicgen (Go, MIT) — https://github.com/iopred/comicgen

### Subagent 3 (Placement algorithms)
- Klein, T. Balloon Placement Guide — https://kleinletters.com/BalloonPlacement.html
- Piekos, N. Blambot Grammar — https://blambot.com/pages/comic-book-grammar-tradition
- Campbell, E. (2007) Rule #3 —
  https://eddiecampbell.blogspot.com/2007/02/last-word-in-speech-balloons_25.html
- Staley, L. (2021) Graphixly Balloon Placement —
  https://graphixly.com/blogs/news/balloon-placement-in-comics
- Chun et al. (2006) LNCS 4292 —
  https://link.springer.com/chapter/10.1007/11919629_58
- Chu & Yu (2013) ACM IMMPD — DOI 10.1145/2505483.2505486
- Yang et al. (2021) ACM TOMM 17(2):55 —
  https://dl.acm.org/doi/fullHtml/10.1145/3440053
- Cao et al. (2014) SIGGRAPH —
  http://www.ying-cao.com/projects/manga_composition/files/composition_paper.pdf

### Caveats and gaps
- No source gives literal pixel-level "pro vs amateur" tail dimensions
  at a 2K canvas. Recommended tail dimensions in §2 are extrapolated
  from Comical-JS constants.
- No IDW Trek-specific letterer commentary found for radio-balloon
  placement convention. The "above listener" rule is general convention,
  not IDW-specific.
- No Python comic-balloon library at production quality surfaced.
  Best technical reference is the TypeScript Comical-JS implementation;
  we'll port the algorithm to Python+PIL.
