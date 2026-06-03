# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.0] — 2026-06-03

**Project repositioning.** Public framing reimagined from "knowledge
graph + chatbots + Episode Writer" to **"end-to-end Star Trek comic
book creation platform."** The story-graph is now presented as the
engine; comic book creation is the headline output. No code changes;
the v0.4.1 pipeline is the v0.5.0 pipeline.

### Changed — README.md
- Tagline rewritten to lead with the end-to-end comic creation story.
- **Page 1 of "The Last Voice of Kethani"** (the v0.4.1 hero artifact
  at `data/poc_comic/stage3/PAGE_1.png`) inserted at the top of the
  page immediately after the tagline, with a credit caption pointing
  to `scripts/build_page_1.py` and `data/COMIC_TECHNIQUES_RESEARCH.md`.
- New "The platform" section with two side-by-side tables: **Story
  creation (stable)** and **Comic book creation (beta — v0.5.0)**.
  Each component links to the relevant module or doc.
- New "Sample episodes" section promoted near the top — three
  full-length teleplays with premise + file links + cost-per-episode +
  cost-to-render-Page-1 numbers.
- New "How it works" section combines the existing GraphRAG diagram
  with a new **comic book pipeline ASCII diagram** (PanelScript →
  Recraft → MiniMax → placer → renderer → composer).
- Prerequisites: added OpenRouter API key requirement for the comic
  side (Recraft V4.1 Pro + MiniMax M3).
- Quickstart: added `scripts/build_page_1.py` to the Linux/macOS flow.
- Usage: replaced the old `src/comic/` preview blurb (which described
  the Stage 1 spike) with a proper `scripts/build_page_1.py` —
  Comic page builder (beta)" subsection.
- Roadmap: Phase 3 (DS9 + behavioral cards) and Phase 4 (Episode
  Writer with three sample episodes) marked done; Phase 5 inserted
  as "Comic book rendering platform — Page 1 done. Next: multi-page
  rendering, character reference images for likeness consistency,
  PDF / CBZ export"; Phase 6 = Voyager + relationship graph.
- License & Attribution: added redistribution restriction for comic
  pages; new paragraph on Recraft-generated panel art.
- Bottom "Built with Hermes" block: updated to mention comic book
  rendering pipeline + multiple sessions (was "single session").
- Version badge bumped 0.4.1 → 0.5.0.

### Code
- `src/config.py`: `__version__` bumped 0.4.1 → 0.5.0.

### Not changed
- Pipeline code, tests, sample episodes, Page 1 render. v0.5.0 is a
  framing release, not a feature release. The v0.4.1 entry below
  documents the actual pipeline shipped.

## [0.4.1] — 2026-06-02

Page 1 of "The Last Voice of Kethani" — full 6-panel page from script
to rendered comic page. Adds research-grounded tail rewrite,
speaker-anchored placement, MiniMax M3 vision, and the Recraft V4.1
art generation pipeline that was held back from v0.4.0.

### Added — Page-builder pipeline
- `scripts/build_page_1.py` — generates 6 contextually-grounded panels
  for Page 1 of "The Last Voice of Kethani" (Captain's log → bridge
  establishing → Worf at tactical → Data at ops → Picard+Riker
  two-shot with Worf comm → Picard commands warp six). Each panel:
  generate art (Recraft V4.1 with locked C-style anchor), vision
  analysis (MiniMax M3), reading-order placement, balloon render,
  page composition into 2x3 grid.
- `data/poc_comic/stage3/PAGE_1.png` — the rendered Page 1 (1400×2165).
- Per-panel artifacts: `p{1-6}_ART.png` (raw Recraft) and
  `p{1-6}_FINAL.png` (with balloons).

### Added — Research-grounded comic rendering
- `data/COMIC_TECHNIQUES_RESEARCH.md` — synthesis from three parallel
  research subagents covering tail construction (Comical-JS arcTail.ts),
  open-source comic balloon implementations, and multi-balloon placement
  algorithms (Klein, Campbell's Rule #3, Blambot, Chu PSO, Yang
  layout). Replaces invention with citation. Sources:
  blambot.com/pages/comic-book-grammar-tradition,
  kleinletters.com/BalloonPlacement.html,
  graphixly.com/blogs/news/balloon-placement-in-comics,
  github.com/BloomBooks/comical-js,
  eddiecampbell.blogspot.com/2007/02/last-word-in-speech-balloons_25.html
- `data/COMIC_PIPELINE_DESIGN.md` — updated with §0 PRIORITY CALLOUT
  ("Panel-level art is NOT assumed satisfactory") and §1 Pipeline flow
  documenting the explicit order of operations.

### Changed — Tail rendering (balloons.py)
- Rewrote `_draw_smooth_tail` per Comical-JS arcTail.ts pattern. The
  single closed polygon is now stroked as ONE continuous closed loop
  (perimeter walk including the final closing segment back to start),
  not two separate open Bezier curves. This was the root cause of the
  "two diverging strokes that never converge" bug.
- Tail length BOUNDED at MAX_TAIL_LENGTH=160px per BBP §4 ("80-120px
  at 1400px canvas"). Previously tail length was proportional to
  speaker distance, producing 800px+ tails that read as two parallel
  lines on long distances.
- Base width increased to 40px (was 28px) for visible taper.
- Tip flat width 4px (was 0px) — Comical-JS BL-8331 workaround to
  prevent stroke overshoot at zero-width tip.

### Changed — Speaker-anchored placement (intelligence.py)
- Replaced "horizontal bands by line index" zone generator with
  `_speaker_zone_candidates` — fan of candidates ABOVE + TO THE SIDE
  of each speaker's face_top, biased toward direction of MORE ROOM
  (panel edge proximity). Sources: Klein "balloons above and away
  from the speaker", Campbell's Rule #3.
- Added `_face_top_points` helper — anchor now uses face_top (cx, y_top)
  not face_center. This is the design decision in research §5 q2:
  tail terminates at upper-forehead, not face center; prevents tail
  tip landing inside speaker's eye.
- Added `_listener_face_for_radio` — for off-panel speakers, biases
  the balloon position toward the on-panel LISTENER (per BBP §3.3
  convention). Eric confirmed this reintroduction was safe because
  the inline `Speaker via Comms:` prefix decouples attribution from
  spatial proximity.
- Added Eddie Campbell test as hard veto: a placement is rejected if
  the balloon would be closer to a non-speaker face than to the
  intended speaker's face.
- Added reading-order CONSTRAINT (not layout axis): bonus when current
  balloon is below or right of prior; penalty when upper-left of prior.
- Side-fallback candidates: when speaker is too high in panel for
  "above" candidates, candidates extend laterally instead.
- Top-edge candidates (BBP Rule 6 — "butt against panel edge") added
  to all lines.
- 20px gutter between balloons (was: exact-overlap check, allowed
  visually touching balloons).
- Removed full-panel grid fallback that papered over impossible
  placements.

### Changed — Vision via MiniMax M3 (intelligence.py)
- Default vision model switched from `anthropic/claude-opus-4.5` to
  `minimax/minimax-m3`. Opus was returning phantom face bboxes on
  starfields/consoles and missing actual character faces on cel-shaded
  comic art. MiniMax correctly identifies faces but reports a different
  internal coordinate system.
- Added coordinate-scale normalization: MiniMax reports a resampled
  image dimension (e.g. 1920×1080) which differs from the actual file
  (e.g. 2688×1536). All bboxes are now scaled from reported-coords to
  actual-coords using PIL-read dimensions.
- Added robust JSON extraction (balanced-brace scan over candidate
  `{...}` regions in the response) for when MiniMax wraps prose around
  its JSON. Includes markdown fence detection + first-parseable-block
  fallback.
- Added `reasoning_content` fallback for empty content responses.
- Strengthened VISION_PROMPT with explicit one-shot JSON example and
  "do not write any explanation, analysis, preamble" directive.

### Changed — PanelScript (panel_script.py)
- `lines=[]` (empty) is now allowed for art-only / establishing-shot
  panels. The placer skips placement entirely; renderer copies art
  straight to FINAL. Test updated to reflect this.

### Added — Recraft V4.1 art generation (imagegen.py)
- `src/comic/imagegen.py` — OpenRouter `recraft/recraft-v4.1-pro`
  client. Generates panel art at 2K resolution (returns 2688×1536 PNG)
  with `image_config.aspect_ratio: "16:9"`. Auto-transcodes Recraft's
  WebP-in-PNG-named-file responses. Locked HOUSE_STYLE constant for
  IDW Mike Johnson era look (chosen via 3-variant A/B/C test in v0.4.0
  WIP). NO_TEXT suffix prevents Recraft from drawing its own balloons.

### Added — Test infrastructure
- `tests/test_intelligence_placer.py` — 16 unit tests for the new
  reading-order placer covering face vetoes (the Stage 2 spiral's
  bug specifically), radio balloon NOT pinned to listener, two-shot
  speaker mapping, reading-order zones, Eddie Campbell test,
  PlacementError contract. Synthetic-data only, no API calls, 0.12s.
- `scripts/test_tail_audit.py` — synthetic 4-balloon tail rendering
  test for visual regression on tail geometry.
- `scripts/test_prompt_variants.py` — A/B/C Recraft prompt variant
  generator (used in v0.4.0 WIP to lock the C-style anchor).
- `scripts/test_two_shot.py`, `test_two_shot_wider.py` — two-shot
  composition validation tests.
- `scripts/regen_panels_2_and_5.py`, `validate_art_with_placer.py` —
  Panel 2 + Panel 5 regeneration + placer validation harnesses.

### Cost summary
- v0.4.1 work cost ~$3.85 OpenRouter spend total (Stage 1 styles + 3
  prompt variants + tight/wider two-shot tests + regen Panel 2/5 +
  vision calls + Page 1 generation). Running total: ~$5.65 of $70.

### Notes
- Character likeness is unreliable in Recraft text-to-image without
  reference images. Page 1 panels render generic Trek-crew silhouettes
  for Worf (no Klingon ridges) and Data (no pale skin tone). Picard
  is recognizable when shown. Future work: Recraft `reference_image`
  with curated character reference shots, or switch to Flux Kontext Pro.
- Stage 2 prior artwork purged per Eric's call: SAMPLE_TNG_..._PAGE_1.png
  deleted (was the v0.4.0 sample of the broken Opus iteration pipeline).
- The italic-radio-test renders from v0.4.0 moved into
  `data/poc_comic/stage2/0.4.1_tests/` for archival.
- The handoff doc `docs/HANDOFF_2026-06-02_Stage2.DEPRECATED.md` remains
  in place as historical reference.

## [0.4.0] — 2026-06-02

Comic pipeline Stage 2 design + radio-balloon italic + PanelScript.
Replaces the broken Opus-iteration approach with a documented, testable
design that targets a Stage 3 full-page composition.

### Added — Comic pipeline design docs
- `data/COMIC_BEST_PRACTICES.md` — research synthesis from Blambot
  (Nate Piekos, foundational rules), Todd Klein (Sandman letterer,
  practical workflow), Graphixly (Liz Staley, beginner-friendly
  placement), Scott McCloud (Understanding Comics: transitions,
  gutters, closure), Comics Devices Library (balloon tag device),
  and the Recraft V4 prompt engineering guide. Each design rule
  in the pipeline traces back to a specific source.
- `data/COMIC_PIPELINE_DESIGN.md` — the v1 design proposal for
  Phases 1–5 of the Stage 2 plan: `PanelScript` data model,
  reading-order placer algorithm, face-veto system, radio-balloon
  italic update, Recraft prompt rewrite, three-scene test matrix,
  execution order with cost ceilings.
- `data/STAGE2_REVISED_PLAN.md` — the new authoritative plan
  replacing the broken `find_balloon_position()` approach. Fix
  the art first, then redesign placement around script reading
  order, delete the combadge-as-anchor branch entirely, verify
  face protection with unit tests, test across 3 scenes before
  any page composition.

### Added — PanelScript data model
- `src/comic/panel_script.py` — explicit script structure
  (`LineType` enum, `ScriptLine`, `PanelScript` dataclasses) with
  authoritative `order` field per line. The placer iterates
  `sorted_lines()` — it never infers reading order from pixel
  positions. Validates: non-empty lines, unique `order` values,
  NORMAL lines must have a speaker, valid `speaker_positions`.
  Helpers: `to_dict()` / `from_dict()` for JSON round-trip.
- `tests/test_panel_script.py` — 15 unit tests (construction,
  validation, sort order, filters, round-trip). Runs in 0.07s,
  no API calls.

### Changed — Radio balloon convention
- `src/comic/balloons.py` — radio/comm balloon body text now
  rendered in regular Komika Text Italic (KOMTXTI_) instead of
  the heavier Bold Italic (KOMTXTBI). The less-bold weight makes
  the italic slant more visible against the upright red inline
  `Speaker via Comms:` tag. Per Eric's call 2026-06-02 — three
  signals now convey "this is a transmission": double outline,
  italic body, inline tag. No tail.
- Removed dead zig-zag helper functions (`_zigzag_line`,
  `_draw_zigzag_tail`) — no callers since radio balloons dropped
  the zig-zag tail. Stale docstring comments referencing zig-zag
  tails updated throughout `balloons.py`.

### Changed — Documentation consistency
- `docs/COMIC_PRODUCTION.md` — five references to zig-zag tails
  on radio balloons replaced with the no-tail rule. Tail section
  reorganized: smooth taper for normal speech, no tail on radio
  (inline prefix conveys the signal). Tellscreen, combadge, and
  TL;DR sections all updated. Cross-references the revised plan
  for the design rationale.
- `README.md` — fixed stale zig-zag reference in the comic
  pipeline feature list. Now consistent with the no-tail rule.
- `docs/HANDOFF_2026-06-02_Stage2.md` deprecated → renamed to
  `docs/HANDOFF_2026-06-02_Stage2.DEPRECATED.md` with a clear
  banner pointing to `data/STAGE2_REVISED_PLAN.md`. The
  deprecated doc's "fix the one anchor bug" recommendation was
  rejected; the revised plan's art-first / script-order approach
  supersedes it.

### Added — Test infrastructure
- `scripts/test_italic_radio.py` — renders two sample radio
  balloons (short + long) to verify the italic body + red tag
  combo. Used to confirm the visual change with Eric before
  committing the renderer change.
- `scripts/test_italic_variants.py` — renders three Komika
  italic variants side by side (Bold Italic / regular Italic /
  Kursive Italic) so the font choice is a visible comparison,
  not a silent decision.

### Notes
- The Stage 2 WIP files (`src/comic/imagegen.py`,
  `src/comic/intelligence.py`, `scripts/render_panel_poc.py`)
  remain uncommitted. They contain the broken Opus-iteration
  approach that the revised plan supersedes. The placer will
  be rewritten against `PanelScript` in the next commit (Task 3
  of the design proposal).
- `data/poc_comic/SAMPLE_TNG_The_Last_Voice_of_Kethani_PAGE_1.png`
  is marked for deletion in the working tree (Eric's purge of
  prior Stage 2 artwork). Not staged in this commit.

## [0.3.0] — 2026-06-02

The Writers' Room. Adds Deep Space Nine, a no-API-key browse mode,
Phase 3 Behavioral Cards, and the headline feature: a multi-agent
Episode Writer that generates full canon-faithful Star Trek teleplays.

### Added — DS9 (Deep Space Nine) corpus
- DS9 scraper (`scripts/fetch_ds9.py`) — polite fetcher for the
  st-minutiae.com screenplay archive (IDs 402–575, skipping the
  missing 473 = "Tears of the Prophets Pt II"). 1.0s delay between
  requests, identifying User-Agent, idempotent skip-existing.
  Saves to `data/raw/ds9_{N}.txt` to avoid collision with TNG's
  bare-numeric raw filenames.
- DS9 ingest orchestrator (`scripts/ingest_ds9.py`) — mirrors
  `ingest_tng.py` with `--parse-only` / `--load-only` flags.
  Reuses `src/parser.py` unchanged (DS9 scripts share the TNG
  screenplay format) and injects `series="DS9"` into each parsed
  JSON before persisting / loading. Episode IDs are the bare source
  numbers (402–575) — no collision with TNG (102–277) or TOS
  (`tos:*` namespace).
- Test fixture (`tests/test_ds9_parse.py`) — 4 assertions on
  episode 402 ("Emissary", the DS9 pilot): title contains
  "Emissary", core cast (SISKO, KIRA, ODO, BASHIR) present, at
  least 200 dialogue lines parsed, series tag = "DS9".

### Corpus growth
- +173 DS9 screenplays (all 7 seasons; only "Tears of the Prophets
  Pt II" is absent from the st-minutiae archive).
- +72,268 DS9 dialogue lines.
- 0 parse failures, 0 thin episodes (<50 lines), 0 load errors.
- Top DS9 speakers: Sisko (9,296), Kira (5,723), Bashir (5,464),
  O'Brien (5,208), Quark (5,103), Odo (4,982), Dax (4,120),
  Worf (2,172), Jake (1,601), Garak (1,590).
- TNG and TOS corpora untouched (still 176 and 80 episodes).
- Combined graph now: 429 episodes across TNG + TOS + DS9.

### Notes
- `src/parser.py` and `src/loader.py` were not modified — the
  existing TNG parser handles DS9 verbatim and the loader is
  series-agnostic.

### Added — Tire-kicker browse mode (no API key required)
- `src/browse.py` and `./trek-browse` launcher (+ `.bat`).
- Renders horizontal-bar charts of character line counts, scene partners,
  episode breakdowns, and word-wrapped longest speeches — all from Neo4j
  alone, zero LLM cost.
- Lets people poke at the corpus before committing to Anthropic setup.

### Added — Behavioral Cards (Phase 3, Layer 2)
- `src/behavioral_extractor.py` — stratified sampling + Claude extraction.
- `scripts/build_behavioral_cards.py` — idempotent orchestrator.
- 20 character `BehavioralCard` nodes created via claude-sonnet-4-5
  for ~$1 total. Each card records core_identity, driving_question,
  speech_patterns, decision_heuristics, hard_limits, signature_phrases,
  emotional_range, intellectual_style.
- `HAS_BEHAVIORAL_CARD` edge links Character → BehavioralCard.
- `src/retriever.py` now pulls the card into the system prompt
  alongside the retrieved canon dialogue — agents get both a derived
  character bible AND raw canonical examples.

### Added — Episode Writer (Phase 5, the headline feature)
- `src/episode_writer.py` — four-agent multi-step pipeline:
  1. **Showrunner** (Opus) writes an outline as structured JSON
  2. **Canon Validator** (Sonnet) flags continuity violations against
     the BehavioralCards and series tonal profile
  3. **Scene Writers** (Opus, one per scene) each receive the
     BehavioralCard and a seed of retrieved canon lines for every
     character in their scene
  4. **Director** (Sonnet) emits structural metadata (act breaks, teaser
     voiceover, tag scene) — Python then deterministically stitches
     the final teleplay, GUARANTEEING no scene content is ever truncated
- `./write-episode` and `./write-episode.bat` launchers.
- Sample episodes committed to the repo:
  - `data/generated_episodes/SAMPLE_TNG_The_Last_Voice_of_Kethani.txt`
    (50,078 chars — preserved alien consciousness moral dilemma)
  - `data/generated_episodes/SAMPLE_TOS_The_Blood_of_Kahless.txt`
    (48,595 chars — Federation colony adopts Klingon practices)
- Cost: ~$1.20–$1.75 per episode at Opus/Sonnet pricing.
- `.gitignore` keeps user-generated episodes private but ships the SAMPLE_*.

### Corpus stats at end of v0.3.0
- TOS:  80 episodes (incl. Menagerie Pt 2 split), 29,316 lines, 472 chars
- TNG: 176 episodes, 70,544 lines, 2,143 characters
- DS9: 173 episodes, 72,160 lines, ~1,000 characters
- **Combined: 429 episodes, ~172,000 lines, ~3,000 characters**
- BehavioralCards: 20 (top characters by line count)

## [0.2.0] — 2026-06-02

The Kirk Update. Adds The Original Series (TOS), cross-series GraphRAG,
end-to-end agent validation, and a `kirk` launcher.

### Added — TOS (The Original Series) corpus
- TOS transcript parser (`src/tos_parser.py`) — BeautifulSoup-based HTML
  parser for chakoteya.net transcripts. Handles `[Location]` scene
  markers, `SPEAKER:` / `SPEAKER [OC]:` cues, mid-paragraph stage
  directions in parens, and bare-paragraph "Captain's Log" narration
  (attributed to KIRK with `parenthetical="Log"`).
- TOS scraper (`scripts/fetch_tos.py`) — polite (1.5s delay,
  identifying User-Agent), idempotent, handles the `16b` Menagerie
  Part 2 oddball production code.
- TOS ingest orchestrator (`scripts/ingest_tos.py`) — mirrors
  `ingest_tng.py` with `--parse-only` / `--load-only` flags. Writes
  parsed JSON to `data/parsed/tos_*.json`.
- Test fixture (`tests/test_tos_parser.py`) — 7 assertions on
  "The Trouble With Tribbles" covering title, namespaced ID,
  metadata, core characters, line count, Captain's Log attribution,
  and scene location extraction.
- Episode-level `series: "TOS"` and `source_type: "transcript"` fields
  so downstream consumers can distinguish transcript vs. screenplay
  provenance (TNG remains `source_type` unset / screenplay).
- Episode IDs namespaced as `tos:<prod_num>` (e.g. `tos:42`,
  `tos:16b`) to avoid collision with TNG's bare-int IDs.

### Corpus growth
- +80 transcripts (79 broadcast episodes; The Menagerie Parts 1+2
  ship as `tos:16` and `tos:16b`).
- +29,352 TOS dialogue lines.
- +3,096 TOS scenes.
- +472 new TOS characters (total now 2,567 across TNG+TOS).
- Top TOS speakers: Kirk (9,324), Spock (4,593), McCoy (2,571),
  Scott (1,382), Sulu (784), Uhura (752), Chekov (474).
- TNG corpus unchanged: still 176 episodes, 70,544 lines.

### Notes
- `src/parser.py` (TNG screenplay parser) and `src/loader.py` were
  not modified — the TOS parser emits the same JSON schema so the
  existing loader handles both series.
- Embeddings for TOS lines will be added in a follow-up `embedder.py`
  run; this changeset only covers Layer-1 graph ingest.

## [0.1.0] — 2026-06-01

First public release. Functional end-to-end pipeline from raw scripts to
GraphRAG-grounded character chatbot, covering all 176 TNG episodes.

### Added
- Screenplay parser (`src/parser.py`) — state-machine over classic
  screenplay format (scene headings, ALL-CAPS character cues,
  parentheticals, dialogue blocks).
- Neo4j loader (`src/loader.py`) — MERGE-based idempotent loader with
  Layer-1 schema: Episode, Scene, Line, Character, Location, Ship.
- Full TNG ingest pipeline (`scripts/ingest_tng.py`) — fetch all 176
  scripts from st-minutiae.com, parse, and load into Neo4j.
- GraphRAG embedder (`src/embedder.py`) — pulls lines from Neo4j with
  full graph metadata as payload, embeds with nomic-embed-text-v1.5
  (local, $0), upserts to Qdrant collection `trek_lines`.
  Point IDs are deterministic (sha1) — re-runs upsert in place.
- GraphRAG retriever (`src/retriever.py`) — two-phase retrieval:
  Qdrant filtered semantic search → Neo4j graph expansion.
- Character chatbot (`src/character_agent.py`) — graph-grounded
  per-turn retrieval, ~3.5k tokens/turn instead of 500k+. Configurable
  model (`--model`), top-k (`--top-k`), conversation `reset`,
  retry-with-backoff on API errors, bounded history.
- Cross-platform support: Linux, macOS (incl. Apple Silicon via MPS),
  Windows. Device auto-detection in `src/device_utils.py`.
- Auth resolution (`src/auth.py`): `ANTHROPIC_API_KEY` env var first,
  Hermes Agent's `~/.hermes/auth.json` as fallback.
- Centralised configuration (`src/config.py`) — all connection strings,
  collection names, tunables overridable via `TREK_*` env vars.
- Cross-platform launchers (`trek`, `trek.bat`, `picard`, `picard.bat`)
  and installer scripts (`install.sh`, `install.bat`).
- Documentation: `README.md`, `AGENTS.md`, `docs/ARCHITECTURE.md`,
  `docs/ONTOLOGY.md` (5-layer schema spec), `docs/PLAN.md`,
  `CONTRIBUTING.md`, this `CHANGELOG.md`.
- CI: GitHub Actions workflow runs syntax/import checks on every push.
- MIT license with attribution notices for CBS/Paramount, st-minutiae,
  nomic, Neo4j, Qdrant, Anthropic.

### Corpus
- 176 TNG episodes (Season 1 through 7)
- 70,544 dialogue lines
- 2,143 characters
- 8,813 scenes
- Top speakers: Picard (13,763), Riker (7,941), Data (6,837),
  Geordi (4,886), Worf (4,096), Beverly (3,613), Troi (3,599).

### Known limitations
- Locations not normalised yet — e.g. BRIDGE / MAIN BRIDGE /
  ENTERPRISE BRIDGE are still distinct nodes. Planned for 0.2.0.
- Only TNG. DS9 (also complete on st-minutiae.com) is the obvious next
  series to ingest. TNG films and partial VOY/ENT scripts also available.
- No behavioral cards yet — characters are voiced purely from retrieved
  dialogue. Layer-2 behavioral models are planned for 0.3.0.
- No Episode Writer yet — that's the headline feature for 1.0.0.

### Created with
[Hermes Agent](https://hermes-agent.nousresearch.com) running Claude
Opus, on Ubuntu (kernel 7.0.0-15-generic), in a single interactive
session. Architecture, code, and documentation all generated together.
