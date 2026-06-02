# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
- Qdrant embeddings for DS9 lines will be produced in a follow-up
  embedder run; this changeset only covers Layer-1 graph ingest.

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
