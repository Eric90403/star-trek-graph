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

### Phase 1 — Spike (this milestone)
- [x] Project skeleton + docker-compose
- [ ] Scrape 5 TNG scripts from st-minutiae.com
- [ ] Parser: scripts → structured JSON (acts, scenes, dialogue, stage directions)
- [ ] Loader: JSON → Neo4j (Layer 1 only)
- [ ] Sample Cypher queries proving the schema works
- [ ] Neo4j Browser bookmarks for exploration

### Phase 2 — Full Corpus + Enrichment
- Scrape all available series (TOS, TNG, DS9, VOY, ENT)
- NER pass to extract ships, species, locations, tech mentions
- Quote node creation + embeddings into Qdrant
- Bi-temporal CharacterState modeling

### Phase 3 — Behavioral Models (Layer 2)
- Claude-generated behavioral cards for top 20 characters
- RAG-backed character chatbot API (FastAPI)
- Simple web UI

### Phase 4 — Narrative Grammar (Layer 3)
- Trope catalog (manual seed + Claude enrichment)
- Beat templates per series
- Conflict topology with tension decay

### Phase 5 — Episode Writer (the headline feature)
- Multi-agent writer's room (Outliner → Writers → Director → Canon Validator)
- Pi-Agent-style harness fork
- Output proper screenplay format

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
