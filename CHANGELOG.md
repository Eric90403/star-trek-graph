# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
