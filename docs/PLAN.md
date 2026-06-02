# Star Trek Graph — Project Plan

## Vision

A generative knowledge graph of Star Trek that is *prescriptive*, not just
descriptive — it records what happened **and** encodes what *could* happen.
This enables:

1. Character chatbots that stay in voice
2. A multi-agent Episode Writer that generates canon-consistent new episodes
3. Community-extensible fan canon with tiered validation

## Five-Layer Ontology

| Layer | Purpose | Examples |
|-------|---------|----------|
| 1. Canonical Facts | Ground truth substrate | Character, Episode, Ship, Quote, Location |
| 2. Behavioral Models | Voice + decision rules | speech_patterns, decision_heuristics, hard_limits |
| 3. Narrative Grammar | Plot mechanics | Trope, Beat templates, Conflict topology, Theme |
| 4. Worldbuilding Rules | Canon constraint engine | Physics, Treaties, Species traits |
| 5. Authorial Intent | Tonal compass | series tonal_profile (TOS frontier, DS9 moral complexity, etc.) |

Plus a `canon_tier` property on every Episode (1=aired, 4=community, 5=AU).

## Phases

### Phase 1 — Full TNG Ingest ✅ COMPLETE
- [x] Project skeleton, docker-compose, GitHub repo
- [x] Screenplay parser (state machine: scene headings, cues, dialogue, parentheticals)
- [x] Neo4j Layer 1 schema: Episode, Scene, Line, Character, Location, Ship
- [x] All 176 TNG episodes fetched and loaded (st-minutiae.com, IDs 102–277)
- [x] 70,544 lines · 2,143 characters · 8,813 scenes in Neo4j
- [x] Cross-platform: Linux / macOS / Windows launchers + install scripts
- [x] ARCHITECTURE.md, AGENTS.md, ONTOLOGY.md full documentation

### Phase 2 — GraphRAG Layer ✅ COMPLETE (v0.1.0–v0.2.0)
- [x] `src/embedder.py` — Neo4j → Qdrant with full graph metadata as payload
- [x] `src/retriever.py` — semantic search + Neo4j graph expansion (2-phase retrieval)
- [x] `src/character_agent.py` — GraphRAG chatbot, ~3.5k tokens/turn vs 500k+
- [x] `src/device_utils.py` — auto-detects CUDA / MPS / CPU across platforms
- [x] **TOS ingest** — chakoteya.net transcript parser + 80 episodes loaded
- [x] **TOS embeddings** — 29,316 lines embedded with `--series` filter
- [x] Combined Qdrant collection: 99,161 points across both series
- [x] Cross-series agent: `--series` flag, dedicated `kirk` launcher
- [x] End-to-end validation: docs/VALIDATION.md
  (Picard + Kirk both pass retrieval, voice, and out-of-canon refusal tests)

### Phase 2.5 — Pre-Promotion Polish (next, before Reddit)
- [ ] Add a demo (asciinema or screenshot in README) so Reddit visitors
      see what they're getting before they install anything
- [ ] No-API-key "tire kicker" mode — let people browse the graph
      without an Anthropic key (e.g. `./trek-browse PICARD` shows top
      lines, episode list, co-stars from Neo4j only)
- [x] **DS9 ingest** — 173 screenplays (IDs 402–575, minus the missing
      473) parsed with the existing TNG screenplay parser and loaded
      as `series="DS9"`. +72,268 dialogue lines. Top speakers:
      Sisko, Kira, Bashir, O'Brien, Quark, Odo, Dax, Worf, Jake, Garak.
      Combined graph: 429 episodes across TNG+TOS+DS9.
      Embeddings to follow in a separate embedder pass.
- [ ] Location normalization — `data/location_aliases.yaml`
      (BRIDGE / MAIN BRIDGE / ENTERPRISE BRIDGE → one Setting+Place pair)

### Phase 3 — Behavioral Models (Layer 2) ✅ COMPLETE
- [x] `src/behavioral_extractor.py` — Claude-derived behavioral cards
- [x] `scripts/build_behavioral_cards.py` — orchestrator with idempotent runs
- [x] Generated `BehavioralCard` nodes for top 20 characters
  (core_identity, driving_question, speech_patterns, decision_heuristics,
  hard_limits, signature_phrases, emotional_range, intellectual_style)
- [x] Retriever wires cards into the system prompt (`HAS_BEHAVIORAL_CARD` edge)
- [x] Total cost: ~$1 with Sonnet-4.5

### Phase 4 — Narrative Grammar (deferred)
- Phase 5 (Episode Writer) shipped without needing this layer.
  Tropes / beat templates / theme catalogs would be polish, not foundation.
  Revisit if generated episodes start feeling formulaic.

### Phase 5 — Episode Writer ✅ COMPLETE (the headline feature)
- [x] `src/episode_writer.py` — four-agent writer's room
  - Showrunner (Opus) writes outline as JSON
  - Canon Validator (Sonnet) flags continuity / character violations
  - Scene Writers (Opus, one per scene) write each scene with
    full BehavioralCard + retrieved canon lines for every character present
  - Director (Sonnet) emits structural metadata only; Python stitches
    the final teleplay without ever truncating scene content
- [x] `./write-episode` / `./write-episode.bat` launchers
- [x] Two sample episodes committed to the repo
  - `SAMPLE_TNG_The_Last_Voice_of_Kethani.txt` — TNG, 50k chars
  - `SAMPLE_TOS_The_Blood_of_Kahless.txt` — TOS, 49k chars
- [x] Cost per episode: ~$1.20–$1.75 at Opus pricing

### Phase 6 — Community Layer
- User-submitted generated episodes
- Voting + canon_tier promotion
- Fork/remix

## Hardware Plan

ThinkPad P52 (current):
- Neo4j + Qdrant + parser pipeline ✅
- Anthropic API for embeddings + generation ✅
- P2000 GPU too small for local inference — not needed in current architecture

Future (with eGPU + RTX Pro 5000 72GB):
- Local Llama/Qwen for the Episode Writer's high-volume scene drafting
- Keep Opus for final voice pass + canon arbitration

## Cost Model

Phase 1: $0 (no API calls in the spike)
Phase 2: ~$10 in Claude/embeddings to enrich the full corpus
Phase 3-5: per-conversation API costs; Sonnet for bulk, Opus for voice

## Tech Stack

| Component | Choice |
|-----------|--------|
| Graph DB | Neo4j 5.26 Community (Docker) |
| Vector DB | Qdrant (shared with TMF, separate collection) |
| Scraper | httpx + BeautifulSoup |
| Parser | Custom Python (regex + state machine) |
| LLM | Anthropic API (Sonnet bulk, Opus voice) |
| API | FastAPI (Phase 3+) |
| Frontend | Telegram bot via Hermes gateway + simple web UI |
| Repo | GitHub, MIT license |

## Open Questions

- Sourcing: is st-minutiae.com complete? Backup sources for missing eps?
- Schema for non-character entities (Q, the Borg Collective) — they're more like forces of nature
- How to handle alternate timelines (Mirror Universe, Kelvin) without polluting prime canon — answer: separate `Universe` node with edges to Episodes
