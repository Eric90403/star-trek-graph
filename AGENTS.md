# Star Trek Graph — Agent & Contributor Guide

## For AI Agents (Hermes, Claude Code, Codex, etc.)

Load this file before working on the project. It tells you where
everything lives, what conventions to follow, and what not to break.

---

## Project Purpose

A generative Star Trek knowledge graph powering:
1. Character chatbots grounded exclusively in canon dialogue
2. A multi-agent Episode Writer that generates new episodes
3. Community fan-canon with tier-based validation

**Key principle:** The LLMs are grounded by the graph, not by training
data. Never let a character agent answer from general knowledge — it must
retrieve from Neo4j/Qdrant and stay within those bounds.

---

## Repository Layout

```
star-trek-graph/
├── AGENTS.md                  ← you are here
├── README.md                  ← user-facing quickstart
├── docker-compose.yml         ← trek-neo4j container
├── picard                     ← launcher script (no venv activation needed)
├── requirements.txt           ← pinned deps
│
├── docs/
│   ├── ARCHITECTURE.md        ← full system design, GraphRAG pattern
│   ├── ONTOLOGY.md            ← five-layer graph schema spec
│   └── PLAN.md                ← phased roadmap with status
│
├── scripts/
│   ├── fetch_scripts.py       ← scrape TNG scripts from st-minutiae.com
│   ├── ingest_tng.py          ← orchestrates fetch → parse → load
│   └── sample_queries.cypher  ← Neo4j Browser exploration queries
│
├── src/
│   ├── __init__.py
│   ├── config.py              ← centralised config + TREK_* env var support + __version__
│   ├── auth.py                ← cross-platform API key resolver
│   ├── device_utils.py        ← auto-detects CUDA/MPS/CPU
│   ├── parser.py              ← screenplay → structured JSON
│   ├── loader.py              ← JSON → Neo4j (MERGE-based, idempotent)
│   ├── embedder.py            ← Neo4j → Qdrant (graph metadata as payload)
│   ├── retriever.py           ← GraphRAG: vector search + Neo4j expansion
│   └── character_agent.py     ← GraphRAG character chatbot (the main agent)
│
├── data/
│   ├── raw/                   ← .gitignored — fetched .txt scripts
│   └── parsed/                ← .gitignored — parsed .json files
│
└── tests/
    └── test_parser.py
```

---

## Infrastructure

| Service | Container | Ports | Credentials |
|---------|-----------|-------|-------------|
| Trek Neo4j | trek-neo4j | HTTP: 7475, Bolt: 7688 | neo4j / trekgraph |
| Qdrant | tmf-qdrant | 6333 | shared with TMF project |

Trek Neo4j starts with: `docker compose up -d` from project root.
Qdrant is already running as a persistent container — do not restart it.
Use Qdrant collection `trek_lines` for this project (not `tmf_*`).

---

## Python Environment

Always use the project venv:
```bash
source .venv/bin/activate
# or use the launcher: ./picard
```

Python 3.11 (pydantic-core won't build on 3.14 yet as of 2026).
`pip install -r requirements.txt` to install all deps.

---

## Embedding Model

**nomic-ai/nomic-embed-text-v1.5** — local, already cached, $0 cost.

```python
from device_utils import get_device
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('nomic-ai/nomic-embed-text-v1.5',
                             trust_remote_code=True, device=get_device())
# IMPORTANT: prefix "search_document: " on ingest
#            prefix "search_query: "    at query time
vecs = model.encode(["search_document: " + text])
```

**Cross-platform device selection (src/device_utils.py):**
- Linux + working CUDA GPU → `cuda`
- macOS Apple Silicon → `mps`
- macOS Intel / CPU-only / broken CUDA arch → `cpu`

`get_device()` probes each backend with an actual tensor op to catch
architecture mismatches (like this machine's P2000 CUDA arch mismatch).
Do NOT use the old `os.environ["CUDA_VISIBLE_DEVICES"] = ""` override —
that was a local workaround now replaced by device_utils.py.

Do NOT use OpenAI or Anthropic embeddings — we have a perfectly good
local model. Do NOT commit model weights to git.

---

## Neo4j Query Conventions

- Use `size()` not `length()` for string/list length in Neo4j 5+
- All writes use `MERGE` (not `CREATE`) — the pipeline is idempotent
- Unique constraints exist on: Episode.id, Character.canonical_name,
  Ship.name, Location.name
- Bolt port is 7688 (not default 7687) to avoid collision with tmf-neo4j

```python
from neo4j import GraphDatabase
driver = GraphDatabase.driver("bolt://localhost:7688",
                              auth=("neo4j", "trekgraph"))
```

---

## The GraphRAG Retrieval Pattern

This is the core of the character agent. See docs/ARCHITECTURE.md for
the full design. The short version:

1. Embed the user query with `"search_query: " + message`
2. Search Qdrant collection `trek_lines` filtered by `speaker=CHARACTER`
3. Take top 40 results — they include graph metadata as payload
4. Expand via Neo4j: pull episode context and co-character relationships
5. Assemble a ~3.5k token context block
6. Pass to claude-opus for generation

Never dump the full character dialogue into context. It doesn't scale.

---

## Canon Tiers

Every Episode node has `canon_tier`:
- 1 = Aired canon
- 4 = Community-generated content
- 5 = Explicit AU / non-canon

Always filter to `canon_tier = 1` by default in character agent queries.
Only include higher tiers if the user explicitly requests it.

---

## Location Normalization (TODO — Phase 2)

Location nodes are currently raw scene headings — noisy and un-normalized.
Example: BRIDGE, MAIN BRIDGE, ENTERPRISE BRIDGE are all the same place.

Do NOT add a normalization pass until the full corpus decision is made
(TNG only vs. all series). The normalization vocabulary lives in
`data/location_aliases.yaml` (not yet created).

---

## LLM Usage Guidelines

| Task | Model | Reason |
|------|-------|--------|
| Character voice generation | claude-opus | Voice fidelity |
| Canon arbitration | claude-opus | Reasoning depth |
| Episode outlining | claude-sonnet | Cheaper, fast iteration |
| Behavioral card generation | claude-sonnet | Bulk, one-time |
| Embeddings | nomic-embed-text-v1.5 (local) | $0, already cached |
| Bulk data enrichment | claude-haiku | Cost efficiency |

---

## What NOT to Do

- Do not use `python3` bare — always use `.venv/bin/python` or activate first
- Do not commit `data/raw/` or `data/parsed/` — they are gitignored
- Do not commit model weights
- Do not use `length()` on strings in Cypher (use `size()`)
- Do not let character agents answer from training data — retrieval only
- Do not restart the tmf-qdrant container — it's shared infrastructure
- Do not add DS9/VOY/Films until TNG GraphRAG is validated end-to-end

---

## Current Corpus State (v0.1.0)

TNG: 176 episodes, 70,544 lines, 2,143 characters — fully loaded in Neo4j.
Embeddings: 70k points in Qdrant collection `trek_lines`.
Top characters: Picard (13,763 lines), Riker (7,941), Data (6,837).

---

## Hermes-Specific Notes

The Hermes skill for this project pattern is saved as:
`~/.hermes/skills/data-science/screenplay-graph-spike/SKILL.md`

When asked to work on this project, load AGENTS.md first, then load
the relevant src/ file you're editing. The docs/ folder is authoritative
on architecture decisions — check it before designing new components.

**Auth resolution (src/auth.py):**
The API key is resolved by `src/auth.py` in this order:
1. `ANTHROPIC_API_KEY` environment variable (preferred — works everywhere)
2. `~/.hermes/auth.json` credential pool (Hermes Agent users)
3. RuntimeError with setup instructions if neither is found

Do NOT hardcode auth paths or API keys. Always import from `src/auth.py`.

---

## Hermes Provenance

This project was designed and built in a single interactive session with
**Hermes Agent** (Nous Research) running Claude Opus on Ubuntu Linux
(kernel 7.0.0-15-generic). Author: Eric Stewart.

Components generated in that session:
- Graph schema (ONTOLOGY.md) and architecture (ARCHITECTURE.md)
- Parser, loader, embedder, retriever, character agents
- Ingest scripts and sample Cypher queries
- All documentation including this file

The project was shared on r/hermesagent as a demonstration of what's
possible with an AI agent working on a technical project end-to-end.
