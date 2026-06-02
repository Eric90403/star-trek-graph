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

### Phase 1 — Spike ✅ COMPLETE
- [x] Project skeleton + docker-compose
- [x] Scrape 5 TNG scripts, parser, loader, sample queries
- [x] Neo4j Layer 1 schema validated
- [x] picard_agent.py — graph-grounded character chatbot (full-context version)
- [x] GitHub repo: https://github.com/Eric90403/star-trek-graph

### Phase 1.5 — Full TNG Ingest ✅ COMPLETE
- [x] All 176 TNG episodes fetched and loaded (IDs 102–277)
- [x] 70,544 lines, 2,143 characters, 8,813 scenes in Neo4j
- [x] Top character: Picard 13,763 lines
- [x] ARCHITECTURE.md, AGENTS.md, PLAN.md updated

### Phase 2 — GraphRAG Layer (next)
- [ ] `src/embedder.py` — pull all lines from Neo4j with graph metadata,
      embed with nomic-embed-text-v1.5 (local, $0), push to Qdrant `trek_lines`
- [ ] `src/retriever.py` — semantic search + Neo4j graph expansion
- [ ] `src/character_agent.py` — replace full-context dump with GraphRAG retrieval
- [ ] Location normalization — `data/location_aliases.yaml` + re-load after full corpus decision
- [ ] Validate: ask Picard questions, confirm answers are graph-grounded

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
