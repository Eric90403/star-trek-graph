# Star Trek Graph — System Architecture

## Overview

Two complementary stores, one retrieval pattern:

```
                    ┌─────────────────────────────────────┐
                    │           USER / AGENT               │
                    └──────────────┬──────────────────────┘
                                   │ natural language query
                          ┌────────▼────────┐
                          │   Retriever     │  src/retriever.py
                          │  (Phase 2+)     │
                          └──┬──────────┬───┘
                             │          │
              ┌──────────────▼──┐    ┌──▼──────────────────┐
              │     Qdrant      │    │       Neo4j          │
              │  trek_lines     │    │   trek-neo4j         │
              │  (semantic)     │    │   (structural)       │
              │                 │    │                      │
              │ vector search   │    │ graph traversal      │
              │ "similar to X"  │    │ "related to X"       │
              │                 │    │                      │
              │ port 6333       │    │ port 7688 (bolt)     │
              │                 │    │ port 7475 (browser)  │
              └──────────────────    └──────────────────────
```

Neo4j and Qdrant are **not redundant** — they answer different questions:

| Store  | Question type | Example |
|--------|--------------|---------|
| Neo4j  | Structural / relational | "What episodes feature both Worf and Gowron?" |
| Qdrant | Semantic / similarity   | "Find lines where Picard talks about duty and sacrifice" |

GraphRAG combines both: Qdrant retrieves semantically similar lines,
Neo4j expands from those results to pull structural context.

---

## Data Pipeline

```
st-minutiae.com                    Neo4j              Qdrant
(plain text scripts)               (graph)            (vectors)

  scripts/fetch_scripts.py  →  data/raw/{id}.txt
  src/parser.py             →  data/parsed/{id}.json
  src/loader.py             →  Episode, Scene,   ←──┐
                               Line, Character,      │
                               Location, Ship        │
                                                      │
  src/embedder.py  ──────────────────────────────────┘
  (reads from Neo4j, embeds with nomic-embed-text-v1.5,
   pushes to Qdrant with graph metadata as payload)
```

---

## Graph Schema (Layer 1 — Canonical Facts)

### Nodes

| Label | Key Properties |
|-------|---------------|
| `Episode` | id, title, series, stardate, writer, director, canon_tier |
| `Scene` | id, scene_num, episode_id |
| `Line` | id, text, parenthetical |
| `Character` | canonical_name |
| `Location` | name |
| `Ship` | name, registry |

### Edges

```
(Line)      -[:SPOKEN_BY]->   (Character)
(Line)      -[:IN_SCENE]->    (Scene)
(Scene)     -[:IN_EPISODE]->  (Episode)
(Scene)     -[:SET_AT]->      (Location)
(Episode)   -[:FEATURES_SHIP]->(Ship)
(Character) -[:APPEARS_IN]->  (Episode)
```

### Planned (Phase 3+)

```
(Character) -[:HAS_BEHAVIORAL_CARD]-> (BehavioralCard)
(Episode)   -[:USES_TROPE]->          (Trope)
(Episode)   -[:HAS_THEME]->           (Theme)
(Character) -[:HAS_TENSION_WITH]->    (Character)
(Rule)      — worldbuilding constraints
```

See ONTOLOGY.md for the full five-layer schema design.

---

## Qdrant Collection: `trek_lines`

Each point = one `Line` node from Neo4j.

### Vector

```
model:      nomic-ai/nomic-embed-text-v1.5  (local, cached, $0 cost)
dims:       768
context:    8192 tokens (handles any speech length)
prefix:     "search_document: " on ingest, "search_query: " at query time
```

### Payload (graph metadata embedded per point)

```json
{
  "neo4j_line_id":   "line:277:42",
  "text":            "Make it so.",
  "speaker":         "PICARD",
  "parenthetical":   "quietly",
  "episode_id":      "277",
  "episode_title":   "All Good Things...",
  "stardate":        "47988.1",
  "scene_num":       42,
  "location":        "BRIDGE",
  "other_speakers":  ["RIKER", "DATA"],
  "series":          "TNG",
  "canon_tier":      1
}
```

The payload enables Qdrant filtered search — e.g. semantic search scoped
to a specific character, episode, location, or scene partner.

---

## GraphRAG Retrieval Pattern

At query time (character agent conversation turn):

```
1. VECTOR RETRIEVAL
   embed("search_query: " + user_message)
   → Qdrant search filtered by speaker=CHARACTER_NAME
   → returns top 40 Line payloads

2. GRAPH EXPANSION
   take episode_ids from those 40 results
   → Neo4j: pull episode context, co-present characters,
     character state at that stardate
   → optional: traverse SPEAKS_WITH edges to get
     relationship history between Picard and the topic entity

3. CONTEXT ASSEMBLY
   character_card (compact, ~500 tokens)
   + retrieved_lines (top 40, ~2000 tokens)
   + graph_expansion (~1000 tokens)
   = ~3500 tokens total  (vs 500k+ for full corpus dump)
```

---

## Character Agent Architecture

```
src/picard_agent.py  (Phase 1 — full context dump, 5 episodes)
  ↓ replaced by Phase 2:
src/character_agent.py  (GraphRAG, full corpus)

At startup:
  - load compact CharacterCard from Neo4j
  - derive behavioral summary (Claude, one-time, cached)

Per conversation turn:
  - embed last user message + last 3 assistant turns
  - retrieve top 40 relevant lines from Qdrant (filtered by speaker)
  - expand context via Neo4j graph hops
  - assemble system prompt
  - call claude-opus for generation
```

---

## Episode Writer (Phase 5)

Multi-agent writer's room. The graph is the "canon bible."

```
Writer's Room Agent  →  queries graph for setting, characters,
                        unused tropes, unresolved tensions
     ↓
Character Agents     →  one per character in the episode,
                        each GraphRAG-grounded
     ↓
Director Agent       →  assembles dialogue into screenplay format
     ↓
Canon Validator      →  checks all facts against Rule nodes in Neo4j
                        before committing
```

---

## Embedding Model

**nomic-ai/nomic-embed-text-v1.5** — already cached at:
`~/.cache/huggingface/hub/models--nomic-ai--nomic-embed-text-v1.5`

```
Parameters:  137M
Disk:        522MB
Dims:        768
Max tokens:  8192
CPU speed:   ~500-800 lines/sec on i7-8850H
GPU:         Auto-detected by src/device_utils.py
Cost:        $0.00
MTEB score:  Beats OpenAI text-embedding-ada-002
License:     Apache 2.0
```

**Device selection (src/device_utils.py):**
The device is auto-detected at runtime — no manual overrides needed:
- Linux/Windows with working CUDA GPU → `cuda`
- macOS Apple Silicon → `mps`
- macOS Intel / CPU-only / broken CUDA arch → `cpu` (this machine's P2000
  has a CUDA arch mismatch with the installed PyTorch build)

`device_utils.get_device()` probes each backend with an actual tensor operation
to catch silent failures. The result is cached after the first call.

Do NOT commit model weights to git. The weights are pulled automatically
by sentence-transformers on first use. The model name is pinned in
`src/embedder.py` and `src/retriever.py`.

To download/verify manually:
```bash
python -c "from sentence_transformers import SentenceTransformer; \
           SentenceTransformer('nomic-ai/nomic-embed-text-v1.5', trust_remote_code=True)"
```

---

## Infrastructure

| Service      | Container     | Ports           | Credentials      |
|--------------|---------------|-----------------|------------------|
| Trek Neo4j   | trek-neo4j    | 7475/7688       | neo4j/trekgraph  |
| TMF Neo4j    | tmf-neo4j     | 7474/7687       | (separate)       |
| Qdrant       | tmf-qdrant    | 6333/6334       | (shared)         |

Trek Neo4j runs via docker-compose.yml in the project root.
Qdrant is shared with the TMF project — use collection `trek_lines`
(not `tmf_*` collections).

Browser access when SSH'd in:
```bash
ssh -L 7475:localhost:7475 -L 7688:localhost:7688 user@host
# then open http://localhost:7475 in local browser
```

---

## Corpus Status

| Source          | Episodes | Lines   | Characters | Status         |
|-----------------|----------|---------|------------|----------------|
| TNG (all 7 seasons) | 176  | 70,544  | 2,143      | ✅ loaded      |
| DS9 (all 7 seasons) | 176  | —       | —          | 📋 Phase 2+   |
| TNG Films           | 4    | —       | —          | 📋 Phase 2+   |
| Voyager (partial)   | 7    | —       | —          | 📋 Phase 3+   |

---

## Cost Model

| Task | Model | Est. Cost |
|------|-------|-----------|
| Embedding 70k TNG lines | nomic-embed-text-v1.5 (local) | $0.00 |
| Per character-agent turn | claude-opus (3.5k tokens) | ~$0.05 |
| Behavioral card generation (20 chars) | claude-sonnet | ~$2.00 one-time |
| Full DS9 + Films embedding | nomic (local) | $0.00 |

Use Sonnet for bulk/outline work, Opus for final voice generation and
canon arbitration.

---

## Provenance

This project was designed and built in a single interactive session with
**[Hermes Agent](https://hermes-agent.nousresearch.com)** (Nous Research)
running Claude Opus on Ubuntu Linux (kernel 7.0.0-15-generic).
Author: Eric Stewart.

Every component in this document — the two-store GraphRAG architecture,
the five-layer graph schema, the nomic-embed-text-v1.5 embedding pipeline,
the character agent with per-turn retrieval, and this document itself —
was designed and generated in that session.

The project was shared on r/hermesagent as a real-world demonstration of
AI-assisted software architecture and implementation.
