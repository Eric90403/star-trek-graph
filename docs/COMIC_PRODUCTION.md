# Comic Writer — Production Reference

This document is the source-of-truth research brief that informed the
design of `src/comic_writer.py`. If you're contributing changes to the
comic pipeline, read this first.

The brief was assembled from Blambot's industry-standard
"Comic Book Grammar & Tradition" by Nate Piekos, comic printer specs,
image-gen API pricing pages, and Star Trek IDW comic conventions.

## TL;DR — The high-leverage moves

1. **Font:** Komika Text (body) + Bangers (SFX/titles). Always ALL CAPS body.
2. **Balloon:** Pure white fill, 3px solid black outline, rounded-rect (radius 25px). NO drop shadow. Tail tapered, terminates 50-60% toward speaker.
3. **Caption box:** Cream/cyan rectangle (#FFE680 or #C5E0EC for Trek log entries), 2px border. Italic text.
4. **Radio balloon (Star Trek!):** Double outline, NO zig-zag tail, inline
   `Speaker via Comms:` prefix in red for combadge/viewscreen/intercom.
5. **Anchor:** Butt balloons against panel top edge — never let them float in negative space.
6. **Post-process:** Posterization + Canny line overlay (30%) + halftone (5%) + grain (3%) makes Flux output read as comic, not painting.
7. **Image prompt suffix:** `"comic book art, bold black ink lines, flat cel-shaded coloring, 1990s Star Trek IDW comic style"`

---

## 1. Page format

| Field | Spec |
|---|---|
| Canvas width | 1400px (target) at digital-equivalent 180-240 dpi |
| Aspect ratio | 1:1.547 (US comic floppy: 6.625" × 10.25") |
| Page height | 2168px (matches 1.547 aspect) |
| Bleed margin | 26px each side |
| Safe-zone inset (keep text inside) | 53px from trim |
| Inter-panel gutter | 20-25px |
| Outer page margin | 50-70px |
| Panel border stroke | 2-3px solid black, consistent across all panels |
| DPI for print | 300 minimum, 600 for line art |
| DPI for screen-only | 150-180 |

### Pacing

Comic page ≈ 20-30 seconds of "screen time."

- Typical TV scene (1-4 min) → 2-4 comic pages
- 30-min teleplay (5 scenes, ~22 min content) → 22-28 page issue
- Dialogue-dense scenes compress more: ~6 panels/page
- Action scenes spread: ~3 panels/page

### Panel grids

- **9-panel (3×3 Watchmen grid):** dense, dialogue-heavy, time-deliberate. Perfect for talky Trek bridge scenes.
- **6-panel (2×3):** the workhorse — most pages
- **4-panel (2×2 or 4 stacked tiers):** bigger beats, action
- **3-tier varying-width:** classic Marvel/DC modern — wide establisher tier + two action tiers
- **Splash (1 panel full page):** act opens, big reveals, episode hooks
- **Variable / open:** emotional climax, fight choreography

Rule of thumb: action pages = fewer/larger panels; dialogue pages = denser grid.

### Shot type rules (Scott McCloud, Will Eisner)

- **Establishing/wide:** first panel of any new scene, location/setting change
- **Medium:** most dialogue (room for 2-shot + balloons)
- **Close-up:** emotional beats, reactions, "punchline" of a page
- **Extreme close-up:** tension, lying, single-word reveal ("Engage.")
- **Over-the-shoulder:** conversation rhythm, POV anchoring
- Never use the same shot type two panels in a row unless deliberate.

---

## 2. Speech balloons

Primary source: Blambot's [Comic Book Grammar & Tradition](https://blambot.com/pages/comic-book-grammar-tradition).

### Balloon shapes

| Shape | Use | Notes |
|---|---|---|
| Smooth oval / rounded-rect | Normal speech | Modern style trends to slightly squared rounded-rect (radius ~25-35px). Pure ellipse looks dated. |
| Cloud / scalloped | Thought | Largely replaced by internal monologue captions since ~2000 |
| Rectangle | Caption | See §3 |
| Jagged / burst | Shouting | Larger text, sometimes bold red |
| Dashed outline | Whispering | |
| Wavy / squiggly | Weak, dying, drugged, ghost | |
| **Double-line ("radio balloon")** — NO tail, inline `Speaker via Comms:` prefix in red | Comms, combadge, viewscreen, intercom | **Crucial for Star Trek** — modern IDW style. The inline prefix conveys the signal; do NOT use a zig-zag tail. |
| Rectangular with computer-style border | AI / computer voice | Data's positronic thoughts often get a unique angular balloon |

### Tails

- **Smooth curved tapered tail:** normal speech
- **Bubble tail (three small circles):** thought
- **No tail, just floating:** off-panel narration in caption box
- **No tail on radio balloons:** the double outline + inline `Speaker via Comms:`
  prefix in red conveys the signal. (Industry historically paired radio
  balloons with zig-zag/lightning tails, but the modern IDW Star Trek style
  drops the zig-zag in favor of the inline speaker tag. See
  `data/STAGE2_REVISED_PLAN.md` for the design rationale.)

**Tail length and pointing:**
- Terminates at ~50-60% of distance between balloon body and speaker's mouth
- Points AT mouth, never covers face
- Never points at hand/torso
- Length: ~80-120px at 1400px canvas

### Off-panel speakers (`WORF (O.S.)`)

Two accepted methods:
- (a) Balloon inside panel; tail extends past panel border, stops pointing toward where speaker would be
- (b) "Off-panel tail": tail bends/jogs at the panel edge (classic Marvel)
- Small directional triangle tail rather than long tail when speaker is far off-panel

Voice on intercom: use radio balloon regardless of on/off panel.

### Reading order

- English/Western: top-to-bottom, left-to-right within each panel
- Letterer must arrange balloons so eye flows naturally — never make reader jump backward
- Connected balloons (same speaker, two beats): join with thin connector bar or stack touching

### Speaker labels

- **Classic style:** NO label inside balloon — speaker identified by tail only
- **Modern indie / webcomic:** small italicized speaker tag inside balloon top
- **Recommendation:** rely on tail. Add inline `PICARD:` tag only for off-panel/radio cases where tail is unclear.

### What separates pro from amateur

| Pro | Amateur |
|---|---|
| Solid black outline, 2-4px, consistent weight | Inconsistent or too-thin/thick outlines |
| Pure white fill #FFFFFF | Cream, gradient, drop shadow |
| 12-18px internal padding | Text crammed to edge |
| Balloon hugs text block, but rounded | Pure ellipse or text-shaped rectangle |
| Tail: smooth taper, no kinks | Pointy triangle tail, lightning bolt for non-electronic |
| Text centered, ~1.05-1.1 line-height | Uneven, oddly spaced text |
| ALL CAPS body | Mixed case (unless deliberate indie style) |
| Bold-italic for emphasis | Plain bold |

The "pasted on" feeling in early POC comes from:
- Too-uniform ellipses
- No slight tail-jitter
- Drop shadows
- Outline too thin/thick relative to text
- Balloons floating in empty space instead of butting against panel borders

Fix: butt balloons against the top of panels often (Blambot "anchoring"),
vary balloon shape slightly per balloon, ensure outline is crisp 1-bit
black against pure white.

---

## 3. Caption boxes

### Types (Blambot)

1. **Location/time:** yellow or cream rectangle, black border. "STARFLEET HQ — STARDATE 47988.0"
2. **Internal monologue:** italic text in caption box. Replaces thought balloons.
3. **Spoken (off-camera dialogue from absent character):** white box, quotation marks, NOT italicized.
4. **Editorial/narrator:** italicized, often yellow.

### Color and style

- Standard: cream/yellow `#FFE680`
- Star Trek log entries: pale blue/cyan `#C5E0EC` evokes LCARS computer readouts
- Border: 2-3px black, sometimes torn-paper edge for flashbacks/dream sequences
- Placement: top-left of panel (reads first); top-right acceptable; bottom only for time-stamp at scene end
- Font: SAME as dialogue, but italic for monologue/editorial. The distinction is the BOX shape, not a different typeface.

### Captain's Log convention

- Almost universally rendered as italic caption boxes
- IDW Star Trek uses pale blue/cyan box with thin black border, sometimes a tiny Starfleet delta in the corner
- Open with: `"CAPTAIN'S LOG, STARDATE 48315.6."` as drop-cap or small-cap opener
- Often spans multiple panels at top of page (split log entry guiding visual sequence)

---

## 4. Fonts

ALL CAPS body is industry standard. Reasons:
- Originated from hand-lettering: uppercase easier at small size with brush/pen
- Uniform x-height = denser readability in cramped balloons
- Distinguishes comic text instantly from book text
- Allows italic to mean "emphasis" without ambiguity

### Free options (rated)

| Font | Source | License | Verdict |
|---|---|---|---|
| **Anime Ace 2.0 BB** | [blambot](https://blambot.com/products/anime-ace-2) | Free for independent/non-profit; paid for commercial | Industry-standard manga-localization look. Clean. |
| **Komika Slim / Display / Text** | [dafont](https://www.dafont.com/komika-slim.font) (Apostrophic Labs) | Free incl. commercial | **Strong default.** Best free analog to CC Wild Words. |
| CC Wild Words | comicraft | Paid only (~$129) | Reference benchmark, don't ship with this |
| Bangers | [Google Fonts](https://fonts.google.com/specimen/Bangers) | OFL | Heavy display only — SFX/titles, NOT body |
| Permanent Marker | Google Fonts | OFL | SFX/handwritten only |
| Comic Neue | Google Fonts | OFL | NOT a pro comic font. Avoid. Reads as Comic Sans alternative. |
| Pangolin | Google Fonts | OFL | Mixed-case casual. Indie/kids feel. Not Trek-appropriate. |
| Whiz Bang BB | Blambot | Free for indie | Display/SFX only |
| Digital Strip | Blambot | Free for indie | Webcomic favorite, modern look |

**RECOMMENDATION:**
- **Body dialogue:** Komika Text (free incl. commercial)
- **SFX and titles:** Bangers (OFL via Google Fonts)
- **Non-commercial fan use only:** Anime Ace 2.0 BB (best pro look)

### Render specs

- Body: 22-26pt at 1400px page width
- Line-height: ~1.05
- Tracking: slightly tight
- Anti-aliasing ON
- Render balloon at 2× and downscale for sharper edges

---

## 5. Sound effects (SFX)

When: punches, explosions, transporters, phaser fire, door whooshes, console alerts.

Star Trek vocabulary: VWOOOSH (transporter), PEW/ZAK (phaser), BWEEP (combadge), KSSSH (atmosphere venting), THWUMP (impact).

How:
- Custom hand-drawn-feel display font (Bangers, Whiz Bang BB)
- Letters often distorted/skewed in motion direction
- 60-120pt at 1400px page width
- Outline: 4-6px black, optional second outline in contrasting color
- Fill: bright color tied to source — yellow phaser, white transporter, orange/red explosion, electric blue force-field
- Placed INSIDE panel, partially overlapping source object
- Can break panel borders for emphasis
- Hollow (transparent center) versions for showing art through letters

---

## 6. Color and tone

**Page background:**
- Pure white `#FFFFFF` for digital-first comic — most modern style
- Cream `#F8F4E8` for "aged paper" — vintage/Hellboy/Sin City. Don't use for Trek.
- For Trek: pure white OR very slight cool tint `#FAFBFC` for "clean future" feel

**Gutter color:**
- Default: same as page background (white)
- Black gutter: signals flashback/dream/somber
- Trek IDW: white gutters with black panel borders

**Panel border:** 2-3px solid black, consistent across all panels on a page. Vary deliberately (thicker for emphasis, none for splash flowing into bleed).

### Making AI art feel like a coherent comic

1. **Posterize** (8-12 levels) + light **Canny edge** overlay at 30% opacity
2. **Color-correct** ALL panels to a shared palette (LUT or limited histogram match)
3. **Halftone/screentone** overlay (5-10% opacity) on midtones
4. **Grain** (Gaussian noise 2-4%) so art doesn't look glossy-CGI
5. Force consistent contrast and saturation per page (auto-levels)
6. **Prompt-side:** ALWAYS include style anchor `"comic book art, bold ink lines, flat cel-shaded color, Mike Allred / Francis Manapul style"`
7. Optional: Flux `--style raw` + Canny ControlNet for line art

---

## 7. Character consistency strategies

### Options (cost as of late 2025/2026)

| Service | Image-ref support | Cost per panel | Quality |
|---|---|---|---|
| Pollinations.ai | Yes (`image` URL param) | Free | Variable |
| Replicate Flux Redux schnell | Reference variation | $0.003 | Mid |
| Replicate Flux Redux dev | Reference variation | $0.025 | Good |
| Replicate Flux 2 pro edit | Multi-reference | $0.05-0.07 | Best |
| **fal.ai Flux Kontext Pro** | Text + reference | **$0.04** | Designed for character consistency |
| fal.ai Flux 2 Pro edit | Multi-reference | $0.045/MP | High |
| Together.ai Flux schnell/dev/pro | NO image-ref | $0.0027-0.04 | N/A for character |
| HF Spaces (IP-Adapter) | Yes | Free | Unreliable |

### LoRA training (one-time per character)

- Replicate (ostris/flux-dev-lora-trainer): ~$2-8 per character
- fal.ai: ~$2
- Needs 10-20 reference images per character

### Strategy comparison for a 24-page comic (~60 panels)

| Strategy | Quality | Cost/24-page | Risk |
|---|---|---|---|
| Detailed prompts + fixed seed + style anchor | 50-65% | $0 (Pollinations) or ~$1.50 (Together schnell) | Faces drift |
| Pollinations image-ref + canonical reference per shot type | 65-75% | $0 | Free tier limits |
| **fal.ai Flux Kontext Pro + ref images** | **80-90%** | **$2.40** | **Best consistency-to-cost** |
| Trained LoRA per character (4 × $3) + Flux dev | 90-95% | $12 train + $13.50 = ~$15 | Highest quality |
| LoRA + Kontext edit pass | 95%+ | ~$15+ | Studio quality |

**RECOMMENDATION (hybrid tier):**

1. **Preview tier:** Pollinations free with image-ref + careful prompt template. **Cost: $0/issue.**
2. **Polish tier:** fal.ai Flux Kontext Pro with curated reference per main character per expression (neutral, intense, smiling, shouting × 4 chars = 16 ref images). **Cost: ~$2.40-3.50 per 24-page comic.**
3. **Premium tier:** LoRA upgrade path: ~$15 total for premium consistency.

### Star Trek IP caveat

Even with free tech, redistribution of comics featuring Stewart/Frakes/Spiner likenesses raises IP issues. This tool is best framed as **personal-use fan generation**, not commercial.

---

## 8. Reference exemplars

1. **IDW Star Trek (2009-present, esp. Mike Johnson run)** — direct reference. Bright clean coloring, 5-6 panel pages, radio balloons for combadge, cyan Captain's Log captions.
2. **Star Trek: Picard - Countdown (IDW, 2019)** — modern Trek visual language, TNG-era characters.
3. **Watchmen (Moore/Gibbons)** — 9-panel grid mastery, caption-driven narration (matches Captain's Log style).
4. **Saga (BKV/Staples)** — modern indie balloon styles, mixed-case lettering by Fonografiks.
5. **Hawkeye (Fraction/Aja)** — restrained 2×4 / 3×3 grids, minimal color palette, exceptional clarity.

### Star Trek-specific conventions

- **Captain's Log:** italic caption, cyan/pale-blue box, opens scenes
- **Combadge dialogue:** ALWAYS radio balloon (double outline, NO zig-zag tail) with
  inline `Speaker via Comms:` prefix in red, even when speaker is right next to
  recipient. The reader identifies the transmitter from the inline tag, not from
  a tail pointing at a combadge. (Updated 2026-06-02.)
- **Viewscreen dialogue:** radio balloon (no tail), placed by script reading
  order. The inline `Speaker via Comms:` prefix identifies the far-end
  speaker; spatial position alone does not.
- **Computer voice ("Working..."):** rectangular angular balloon, often light grey/cyan fill
- **Alien language:** bracketed text `<This is honorable>` with asterisk + editorial caption `*Translated from Klingon`
- **Tech terminology:** stays unformatted — "warp factor seven" not italicized

---

## 9. Sources

- Blambot Comic Book Grammar & Tradition — https://blambot.com/pages/comic-book-grammar-tradition
- Blambot Better Letterer Tips — https://blambot.com/pages/lettering-tips
- Comic Page Size Guide — https://www.automateed.com/comic-book-page-size
- Creator Resource on Bleeds — https://www.creatorresource.com/on-bleeds-and-clearance/
- fal.ai Flux pricing — https://fal.ai/flux and https://fal.ai/pricing
- Replicate Flux Redux — https://replicate.com/black-forest-labs/flux-redux-dev
- Pollinations API docs — https://github.com/pollinations/pollinations/blob/main/APIDOCS.md
- Memory Alpha (Captain's Log) — https://memory-alpha.fandom.com/wiki/Captain%27s_log
- Dafont Komika — https://www.dafont.com/komika-slim.font
- Dafont Anime Ace BB — https://www.dafont.com/anime-ace-bb.font
- Google Fonts Bangers — https://fonts.google.com/specimen/Bangers
