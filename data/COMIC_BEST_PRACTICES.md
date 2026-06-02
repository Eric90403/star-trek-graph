# Comic Book Best Practices — Research Synthesis

**Date:** 2026-06-02
**Purpose:** Establish the design rules that will govern the Stage 2+ comic
pipeline code (PanelScript, reading-order placer, face-veto tests, Recraft
prompting, post-processing). Each rule traces to a source.
**Scope:** Foundationally: balloon placement, reading order, face protection,
radio balloon convention, AI art prompting for IDW Star Trek, post-processing,
page composition. Does NOT cover: writing, inking, coloring by hand,
printing/distribution.

**Status:** DRAFT — to be reviewed and refined with Eric before any code is
written against it. Supersedes nothing; complements `docs/COMIC_PRODUCTION.md`
(which is the broader research brief).

---

## Sources (numbered for citation)

1. **Blambot "Comic Book Grammar & Tradition"** — Nate Piekos, industry-standard
   reference. https://blambot.com/pages/comic-book-grammar-tradition
2. **Todd Klein "How to place balloons"** — legendary letterer (Sandman, Swamp
   Thing). https://kleinletters.com/BalloonPlacement.html
3. **Graphixly "Balloon Placement in Comics"** — Liz Staley (Clip Studio Paint
   author), practical beginner-friendly guide.
   https://graphixly.com/blogs/news/balloon-placement-in-comics
4. **Scott McCloud "Understanding Comics" (1993)** — six panel transitions,
   gutters, closure. Secondary source:
   https://understandingcomics177.wordpress.com/about/1-2/2-2/
5. **Comics Devices Library "Balloon tag"** — Reimena Yee. Modern concept for
   disembodied speaker identification. https://comicsdevices.com/balloon-tag/
6. **Recraft V4 Prompt Engineering Guide** — official, design-logic approach
   for our image-gen model. https://www.recraft.ai/blog/prompt-engineering-guide
7. **LlamaGen "Ultimate Guide to AI Character Consistency 2025"** — vendor
   source, use cautiously. https://llamagen.ai/blogs/ai-character-consistency-solutions-2025

---

## 1. TL;DR — the rules that govern our code

| # | Rule | Source | Code impact |
|---|------|--------|-------------|
| 1 | Faces are sacred — never cover a face of an important character | [2, 3] | **Hard veto** in placer |
| 2 | English reading order: top-left → bottom-right, both within panels and across | [2, 3] | **Reading-order placer** anchors balloons to script order, not pixel proximity |
| 3 | Character on the LEFT speaks first | [2] | Two-shot placer puts first balloon near left character |
| 4 | Balloon tail points at the SPEAKER'S MOUTH, terminates 50-60% of the way there | [1, 3] | Tail geometry in `balloons.py` |
| 5 | Never cover hands, feet, or important detail | [2, 3] | **Soft penalty** in placer |
| 6 | "Butting" balloons against a panel edge is the best space-constraint tool | [1] | Placer should prefer edge-adjacent positions when text overflows |
| 7 | Don't cross balloon tails — "looks rather silly" | [2, 3] | Veto on tail-crosses-tail |
| 8 | A disembodied balloon (off-panel speaker) needs a tag or distinct style to identify the speaker | [5] | Radio balloon convention: inline `Speaker via Comms:` prefix in red |
| 9 | Plan text BEFORE art, not after (P. Craig Russell tradition) | [2, 3] | **Pre-render text fitting** in placer; font size and wrap width pre-computed |
| 10 | "There are often several ways to solve any placement problem — work through them" | [2] | Placer runs width-retry loop and scores multiple candidates, not first-fit |

These are the rules the code will enforce and follow. Each maps to a
concrete code construct.

---

## 2. Reading order — the algorithm

**The problem:** A panel has multiple balloons. Which goes where?

**The industry decision procedure** (synthesized from [2, 3]):

1. **Establish the dialogue sequence.** The script tells you who speaks first.
   This is authoritative — reading order within a panel follows script order,
   not visual proximity to a body part.

2. **First balloon goes top-left** (Western convention), or top-center for
   single-balloon panels. NOT bottom-left, NOT next to the speaker's face.

3. **Subsequent balloons go down and/or right of the previous.** "Down" is
   preferred when panels are tall; "right" when panels are wide. The eye
   follows the implied trail.

4. **In a two-shot:** the left character speaks first (Rule 3). The first
   balloon sits near the left character's head, ABOVE the head and to the
   upper-left. The reply sits near the right character's head, or below
   the first balloon. NOT floating in dead space between them.

5. **For an off-panel / comm / radio balloon:** the balloon's POSITION is
   determined by script order, not by a "listener anchor." The TAIL is
   optional or absent (see §5). The reader identifies the speaker from the
   inline tag, not from a tail pointing at a combadge.

6. **If balloons would overlap:** adjust positions to flow, don't re-order
   script. Overlap is OK; crossed tails are NOT.

**For our placer code:** This becomes a position candidate generator. For
each script line in order:
- Generate ~30 candidate positions: upper-left zone first, then down/right
  pattern for subsequent lines
- Score each against hard vetoes (faces, edges, prior balloons) and soft
  preferences (reading-order zone, speaker proximity, empty regions)
- Pick highest-scoring candidate
- Width-retry loop (try narrower widths first, re-score) — from
  existing `find_balloon_position()` logic

---

## 3. Face protection — the hard veto

**Rules from [2, 3]:**
- "If you must [cover a figure]: avoid hands and feet, never cover faces of
  important characters" (Klein)
- "Make sure balloon tails don't cross over another character's face or neck"
  (Staley)

**For our code:** This becomes a set of pixel-level checks, run on every
candidate position:

- **Face overlap:** AABB overlap between balloon rect and any face bbox
  with zero padding → veto. (Faces are sacred; even 1 pixel is too many.)
- **Tail crosses face:** The tail's polyline intersects any face bbox
  (other than the speaker's own face) → veto.
- **Neck overlap:** AABB overlap between balloon rect and a face bbox
  padded by ~20px vertically to capture the chin/jaw area → soft veto
  (penalize, not hard-veto, since neck is not sacred).
- **Body overlap:** AABB overlap between balloon rect and a body bbox →
  soft penalty, not veto (covering a torso/limb is acceptable per Klein).

**Speaker's own face is exempt** from the tail-crosses-face veto (the tail
points at them — that's correct). The balloon body itself can NEVER cover
the speaker's own face (the speaker must remain visible).

**Test strategy (from [2]):** "Test with a friend" — but for our automated
pipeline, we can write deterministic unit tests that place a balloon over
a known face bbox and assert the placer vetoes it.

---

## 4. Balloon placement conventions (shape, tail, color)

From [1] (Blambot):

- **Shape:** Rounded-rect, radius 25-35px at 2K source. NOT pure ellipse
  (reads dated). NOT sharp rectangle (reads as caption).
- **Fill:** Pure white #FFFFFF. NOT cream, NOT gradient, NOT drop shadow.
- **Outline:** Solid black 2-4px (we use 5px at 2K source). Consistent
  weight across a page.
- **Tail:** Smooth curved taper from balloon edge to 50-60% of the distance
  to the speaker's mouth. Terminates with a point, not a flat edge.
- **Padding:** 14-18px internal padding around text. (We use 28/22 at 2K
  — about 2x the Blambot recommendation, scaled for our larger canvas.)

**Anti-patterns (Blambot's "amateur tells"):**
- Too-uniform ellipses (looks like a stamp)
- Drop shadow (reads as floating UI element)
- Outline too thin or too thick relative to text
- Balloon floating in empty space — butting against an edge is preferred

**Tails we explicitly do NOT use:**
- ~~Zig-zag / lightning tail~~ — removed per Eric's hard rule. Modern IDW
  Trek style drops the zig-zag in favor of the inline `Speaker via Comms:`
  prefix. See §5.
- ~~Bubble tail (three small circles)~~ — only for thought balloons, which
  we don't use (replaced by captions per modern convention).

---

## 5. Radio balloon design — the inline-prefix decision

**Industry tradition ([1]):**
- Radio balloons (combadge, viewscreen, intercom) are recognized by
  **italic text** within a standard balloon
- The italics distinguish transmitted voice from in-person speech
- Tails historically have been zig-zag/lightning to emphasize the electronic
  origin, but this is convention, not requirement

**The modern alternative ([5] + Eric's hard rule):**
- Replace the zig-zag tail with an **inline speaker tag** in red,
  e.g., `WORF via Comms: We have arrived at the relay station.`
- Drop the tail entirely (it would point at a combadge pixel, which is
  unreliable)
- Keep the double outline (still indicates "this is transmitted, not spoken")
- The reader identifies the speaker from the inline tag, not from a tail

**Why this works:**
- [5] establishes that "balloon tags" are an established comic device for
  disembodied speakers (off-panel radio, talking heads, walky-talky). The
  IDW Star Trek convention is to put the tag inline with the dialogue.
- Removing the tail eliminates a whole class of placement bugs
  (where does the tail point? what if the combadge moves? what if the
  listener is on the other side of the panel?).
- The double outline still conveys "this is a transmission" — a
  distinguishing visual that doesn't require spatial reasoning.

**For our code:** Radio balloon is a distinct `BalloonType` with:
- Double outline (already implemented)
- NO tail
- Inline `f"{speaker.title()} via Comms: {text}"` prefix
- Prefix rendered in red, body text in normal text color
- Placed by reading order, NOT by listener anchor

This is a documented departure from Blambot's traditional convention, but
it aligns with the modern IDW Star Trek house style and with the Comics
Devices Library's formal "balloon tag" device.

---

## 6. AI art prompting for the IDW Star Trek look

From [6] (Recraft V4 guide), the prompt structure should be **global to local**:

| # | Element | Our application |
|---|---------|-----------------|
| 1 | Core concept | "TNG bridge two-shot: Picard and Riker at command stations" |
| 2 | Background/environment | "LCARS console displays, soft blue ambient lighting, starfield on main viewscreen" |
| 3 | Primary subject framing | "Picard standing at command chair, Riker at conn station, both chest-up, filling lower 50% of frame" |
| 4 | Physical attributes | "Picard in red command uniform, bald, dignified; Riker in gold ops uniform, beard, animated" |
| 5 | Secondary subjects | "Background crew members at distant stations, slightly out of focus" |
| 6 | Lighting | "Cool blue rim lighting from overhead, warm amber accent from aft turbolift" |
| 7 | Camera/depth/contrast | "Cinematic 16:9 composition, shallow depth of field, medium shot" |
| 8 | Mood/composition | "Quiet authority, mid-scene contemplative, IDW Star Trek 2009-2018 house style" |

**Specific corrections to our previous prompts (per [6]):**
- ❌ "Negative space" / "empty area for balloons" — Recraft interprets this
  as "leave the panel mostly empty." Results: vast white void, characters
  tiny in the frame.
- ✅ Replace with composition density directives: "characters filling lower
  50-60% of frame," "bridge set dressing visible in background," "console
  displays and ambient lighting filling the space."

**Style anchor (Mike Johnson era IDW Star Trek):**
- "modern 2009-2018 IDW Star Trek comic art by Mike Johnson and Tony Shasteen,
  bold black ink lines, flat cel-shaded coloring, cinematic lighting"
- Plus: `"comic book art, bold black ink lines, flat cel-shaded coloring"`
  (from our existing `HOUSE_STYLE` constant — keep this)

**Negative prompts to always include:**
- "no text, no speech balloons, no captions, no letters, no words" —
  prevents Recraft from drawing its own balloons

---

## 7. Post-processing for AI→comic

From [6] (Recraft) + our existing `panels.py`:

Recraft V4 output is too "clean CGI" out of the box. The standard fix stack:

1. **Posterize** to 8-12 levels — flattens gradients into cel-shaded bands
2. **Canny edge overlay** at 30% opacity — adds ink line emphasis
3. **Halftone** at 5-10% opacity on midtones — adds print-comic texture
4. **Gaussian grain** at 2-4% — removes CGI gloss
5. **Auto-levels** per panel — consistent contrast across the page

We already have this in `panels.py`. Verify it stays in the pipeline.

---

## 8. Page composition rules

From [2, 4]:

- **Panels in horizontal rows** are easiest to read (grid format).
- **Vertical + horizontal panel mixes** are harder — extra care needed.
- **Reading direction within a page:** top-left to bottom-right, generally.
- **Visual surprises (SFX, big reveals) work best at the top** of a page.
- **Transitions between panels** (McCloud): action-to-action is most common
  in fight/action, subject-to-subject in dialogue scenes. For our talky
  TNG bridge scenes, expect mostly subject-to-subject.

**For Stage 3 (6-panel page):**
- A 2x3 or 3x2 grid is the workhorse — easy to read, fits dialogue well.
- Reserve splash/irregular grids for high-impact moments.
- Lead the eye with an implied trail of balloons; use clear "Z" pattern
  through the panels.

---

## 9. What we are explicitly NOT doing (and why)

| Anti-pattern | Why we're not doing it | Source |
|--------------|------------------------|--------|
| Zig-zag / lightning tails on radio balloons | Modern IDW Trek style uses inline tag instead; eliminates anchor bugs | [5] + Eric's hard rule |
| Comb badge-as-anchor for radio balloon tail placement | Combadge is an unreliable locator; the inline tag conveys the speaker | [2, 3] + Eric's hard rule |
| Covering faces of important characters | Industry hard rule | [2, 3] |
| Crossing balloon tails | "Looks rather silly" | [2, 3] |
| Pointing tails at hands/feet/body | Tails must point at mouth | [1, 3] |
| "Negative space" / "empty area" prompting for AI art | Causes vast white voids; opposite of what we want | [6] |
| Thought balloon (cloud) for internal monologue | Replaced by italic caption in modern style | [1] |
| Drop shadows on balloons | Amateur tell, reads as UI element | [1] |
| First-fit balloon placement (no retry) | Industry does width-retry and scores multiple candidates | [2] |
| Speech balloons rendered AFTER art (no pre-planning) | Tradition (P. Craig Russell) is to plan text first | [2, 3] |

---

## 10. Open questions for Eric

These came up during research and need his call before code:

1. **Font:** Blambot's Anime Ace 2.0 BB is the "industry look" for Star Trek
   (used in DS9/VOY comic adaptations historically) but is free-for-indie
   only. We use Komika Text (free incl. commercial). Stick with Komika, or
   invest in Anime Ace for premium look?

2. **Italic for radio balloon body text:** Blambot says radio balloon text
   is traditionally italic. Our current impl uses bold-red inline tag +
   non-italic body. Should we add italics to the body text as a secondary
   signal, or keep it as is (inline tag is sufficient)?

3. **IDW Mike Johnson era visual reference:** I couldn't verify whether the
   Mike Johnson Star Trek comics specifically use zig-zag tails or not
   (visual reference, not text). Our hard rule (no zig-zag) is well-aligned
   with the modern trend per [5], but if Eric wants strict adherence to a
   specific IDW issue's look, that might override. Visual check needed.

4. **Page density target:** A 2x3 grid = 6 panels, each ~680x500 at the
   1400px page width. Blambot/Klein say dense dialogue scenes fit ~6
   panels/page. For our talky bridge scenes, is 6 panels right, or push
   to 9 (Watchmen-style) for more dialogue room?

---

## 11. Sources & further reading

- [1] Blambot "Comic Book Grammar & Tradition" —
  https://blambot.com/pages/comic-book-grammar-tradition
- [2] Todd Klein "How to place balloons" —
  https://kleinletters.com/BalloonPlacement.html
- [3] Graphixly "Balloon Placement in Comics" —
  https://graphixly.com/blogs/news/balloon-placement-in-comics
- [4] McCloud "Understanding Comics" (1993) — six transitions, gutters,
  closure; secondary source
  https://understandingcomics177.wordpress.com/about/1-2/2-2/
- [5] Comics Devices Library "Balloon tag" —
  https://comicsdevices.com/balloon-tag/
- [6] Recraft V4 Prompt Engineering Guide —
  https://www.recraft.ai/blog/prompt-engineering-guide
- [7] LlamaGen "Ultimate Guide to AI Character Consistency 2025" — vendor
  source, treat stats as marketing until independently verified
- Blambot "Better Letterer" infographic series (image-only) —
  https://blambot.com/pages/lettering-tips

**Caveats:**
- Sources [4] (McCloud) was accessed via secondary summary; primary text
  not directly read. Concepts cited (six transitions, closure, gutters) are
  universally established in comics theory.
- Source [7] (LlamaGen) is vendor marketing material. Their "96% consistency
  score" is from their own benchmark. We do not use their product; we cite
  for context on the 2025-2026 character-consistency landscape.
- IDW Mike Johnson era visual reference: not directly verified in this
  research pass. Visual check recommended before finalizing the no-zigzag
  decision for the chosen house style.
