# Star Trek Graph

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Version 0.1.0](https://img.shields.io/badge/version-0.1.0-green.svg)](CHANGELOG.md)
[![Built with Hermes Agent](https://img.shields.io/badge/built%20with-Hermes%20Agent-blueviolet)](https://hermes-agent.nousresearch.com)

> "The sky's the limit." — Jean-Luc Picard, *All Good Things...*

A knowledge graph of every line ever spoken in *Star Trek: The Next Generation* —
176 episodes, 70,544 lines, 2,143 characters — powering GraphRAG-grounded
character chatbots and an AI episode writer, all running locally for $0 in
embedding costs.

**Created with [Hermes Agent](https://hermes-agent.nousresearch.com) on Ubuntu
(kernel 7.0.0-15-generic)**

> This project was designed and built interactively with
> [Hermes Agent](https://hermes-agent.nousresearch.com) running Claude Opus on
> Ubuntu. The architecture, code, and documentation were all generated in a
> single session.

---

## What is this?

Three things in one repo:

| Component | What it does |
|-----------|-------------|
| **Knowledge Graph** | All 176 TNG episodes loaded into Neo4j. Episodes, scenes, lines, characters, locations, ships — all connected. |
| **Character Chatbots** | Talk to Picard, Worf, Data, or any of 2,143 characters. The LLM is grounded *exclusively* in canon dialogue — no hallucinated backstory. |
| **Episode Writer** *(Phase 5)* | Multi-agent writer's room where character agents collaborate to draft new canon-faithful episodes. |

The trick is **GraphRAG** (Retrieval-Augmented Generation from a graph):
instead of dumping 500,000 tokens of dialogue into the context window,
the system embeds your question, retrieves the 40 most semantically
relevant lines from Qdrant, then expands those into structural episode
context from Neo4j. ~3,500 tokens per turn instead of 500,000+.

```
Your question
     │
     ▼
 Embed with nomic-embed-text-v1.5 (local, $0)
     │
     ├──► Qdrant (semantic)          Neo4j (structural)
     │    "lines similar to query"   "episode + relationship context"
     │                │                          │
     └────────────────┴──────────────────────────┘
                      │
                      ▼
              ~3,500 token context block
                      │
                      ▼
              Claude Opus → character response
```

---

## Prerequisites

- **Python 3.11** (pydantic-core does not build on 3.14+ yet — use pyenv if needed)
- **Docker** (Docker Desktop on macOS/Windows, Docker Engine on Linux)
- **git**
- **Anthropic API key** — get one at [console.anthropic.com](https://console.anthropic.com/)

---

## Quickstart

### Linux / macOS

```bash
git clone https://github.com/yourname/star-trek-graph.git
cd star-trek-graph

# Install everything (Python venv + pip + Docker images)
bash install.sh

# Set your API key
export ANTHROPIC_API_KEY=sk-ant-...

# Start Neo4j
docker compose up -d

# Load TNG episodes into Neo4j (first time only, ~10 min)
.venv/bin/python scripts/ingest_tng.py

# Build vector embeddings (first time only, ~7 min on CPU)
.venv/bin/python src/embedder.py

# Talk to Picard
./trek

# Talk to Worf with more context
./trek --character WORF --top-k 60
```

### Windows

```bat
git clone https://github.com/yourname/star-trek-graph.git
cd star-trek-graph

REM Install everything
install.bat

REM Set your API key (PowerShell)
$env:ANTHROPIC_API_KEY = 'sk-ant-...'

REM Start Neo4j
docker compose up -d

REM Load TNG episodes (first time only, ~10 min)
.venv\Scripts\python.exe scripts\ingest_tng.py

REM Build vector embeddings (first time only, ~7 min on CPU)
.venv\Scripts\python.exe src\embedder.py

REM Talk to Picard
trek

REM Talk to Data with 60 retrieved lines
trek --character DATA --top-k 60
```

---

## Usage

### `./trek` — GraphRAG character chatbot (recommended)

```
./trek                          Talk to Picard (default)
./trek --character WORF         Talk to Worf
./trek --character DATA         Talk to Data
./trek --character BEVERLY      Talk to Dr. Crusher
./trek --character TROI         Talk to Counselor Troi
./trek --character GEORDI       Talk to Geordi La Forge
./trek --character RIKER        Talk to Commander Riker
./trek --top-k 60               Retrieve 60 lines per turn (more context, slower)
```

The agent retrieves only the lines most relevant to your current question —
efficient, accurate, and it scales to any character in the corpus.

Every character responds from canon dialogue only. If you ask Worf about something
not in the graph, he'll tell you he has no record of it. That's the point.

### `./picard` — Legacy full-context agent

```
./picard                        Picard (loads ALL 13,763 of his lines at startup)
./picard --character RIKER      Any character — but big characters hit token limits
```

The original Phase 1 implementation. Useful for small characters (under ~2,000 lines)
where loading everything at once is fine. For Picard/Riker/Data, use `./trek`.

### Ingest scripts

```bash
# Fetch raw scripts from st-minutiae.com
.venv/bin/python scripts/fetch_scripts.py

# Full pipeline: fetch + parse + load into Neo4j
.venv/bin/python scripts/ingest_tng.py

# Embed all lines into Qdrant
.venv/bin/python src/embedder.py

# Embed only one character (useful for testing)
.venv/bin/python src/embedder.py --speaker PICARD

# Dry run — count lines without embedding
.venv/bin/python src/embedder.py --dry-run
```

---

## Sample Queries (Neo4j Browser)

Open Neo4j Browser at **http://localhost:7475** (username: `neo4j`, password: `trekgraph`).

```cypher
-- How many lines does each character have?
MATCH (l:Line)-[:SPOKEN_BY]->(c:Character)
RETURN c.canonical_name AS character, count(l) AS lines
ORDER BY lines DESC LIMIT 20

-- What episodes feature both Worf and Gowron?
MATCH (w:Character {canonical_name: "WORF"})-[:APPEARS_IN]->(e:Episode)
MATCH (g:Character {canonical_name: "GOWRON"})-[:APPEARS_IN]->(e)
RETURN e.title, e.stardate ORDER BY e.stardate

-- Find all of Picard's lines mentioning duty
MATCH (l:Line)-[:SPOKEN_BY]->(c:Character {canonical_name: "PICARD"})
WHERE toLower(l.text) CONTAINS "duty"
RETURN l.text LIMIT 25

-- Who shares the most scenes with Data?
MATCH (data:Character {canonical_name: "DATA"})<-[:SPOKEN_BY]-(:Line)
      -[:IN_SCENE]->(s:Scene)<-[:IN_SCENE]-(:Line)
      -[:SPOKEN_BY]->(other:Character)
WHERE other.canonical_name <> "DATA"
WITH other.canonical_name AS partner, count(DISTINCT s) AS scenes
ORDER BY scenes DESC LIMIT 10
RETURN partner, scenes

-- Episode stats: lines per episode, Season 2
MATCH (e:Episode {season: 2})<-[:IN_EPISODE]-(:Scene)<-[:IN_SCENE]-(l:Line)
RETURN e.title, count(l) AS lines ORDER BY lines DESC
```

Full sample query file: `scripts/sample_queries.cypher`

---

## Architecture

Two complementary stores, one retrieval pattern:

```
                   ┌─────────────────────────────────────┐
                   │           USER QUESTION              │
                   └──────────────┬──────────────────────┘
                                  │ natural language
                         ┌────────▼────────┐
                         │   Retriever     │  src/retriever.py
                         │  (GraphRAG)     │
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
             └─────────────────┘    └──────────────────────┘
```

Neo4j and Qdrant answer different questions:

| Store  | Question type | Example |
|--------|--------------|---------|
| Neo4j  | Structural / relational | "What episodes feature both Worf and Gowron?" |
| Qdrant | Semantic / similarity   | "Find lines where Picard talks about duty and sacrifice" |

### Data Pipeline

```
st-minutiae.com                    Neo4j              Qdrant
(plain text scripts)               (graph)            (vectors)

  scripts/fetch_scripts.py  →  data/raw/{id}.txt
  src/parser.py             →  data/parsed/{id}.json
  src/loader.py             →  Episode, Scene,   ─────────────┐
                               Line, Character,               │
                               Location, Ship                 │
                                                              │
  src/embedder.py  ────────────────────────────────────────── ┘
  (reads from Neo4j, embeds with nomic-embed-text-v1.5,
   pushes to Qdrant with full graph metadata as payload)
```

### Graph Schema (Layer 1)

```
(Line)      -[:SPOKEN_BY]->   (Character)
(Line)      -[:IN_SCENE]->    (Scene)
(Scene)     -[:IN_EPISODE]->  (Episode)
(Scene)     -[:SET_AT]->      (Location)
(Episode)   -[:FEATURES_SHIP]->(Ship)
(Character) -[:APPEARS_IN]->  (Episode)
```

Full schema spec: `docs/ONTOLOGY.md`

### Embedding Model

**nomic-ai/nomic-embed-text-v1.5** — runs locally, costs $0.

- 768 dimensions, 8192 token context
- Apache 2.0 license
- Beats OpenAI text-embedding-ada-002 on MTEB
- ~500–800 lines/sec on CPU (i7-8850H)
- Device auto-detected: CUDA > MPS (Apple Silicon) > CPU

---

## Corpus Status

| Source | Episodes | Lines | Characters | Status |
|--------|----------|-------|------------|--------|
| TNG (all 7 seasons) | 176 | 70,544 | 2,143 | loaded |
| DS9 (all 7 seasons) | 176 | — | — | Phase 3+ |
| TNG Films | 4 | — | — | Phase 3+ |
| Voyager | 172 | — | — | Phase 4+ |

Top characters by line count: Picard (13,763), Riker (7,941), Data (6,837),
Worf (5,088), Troi (4,991), Geordi (4,721), Beverly (3,892).

---

## Roadmap

See `docs/PLAN.md` for the full phased roadmap with status. The short version:

- **Phase 1** (done): 5-episode spike, parser, loader, Picard full-context agent
- **Phase 2** (done): Full TNG corpus, GraphRAG retriever, character_agent
- **Phase 3**: DS9 + TNG Films, behavioral cards, location normalization
- **Phase 4**: Voyager, character relationship graph, fan-canon tier
- **Phase 5**: Multi-agent Episode Writer with canon validation

---

## Contributing

Pull requests welcome. Before you open one:

1. Read `AGENTS.md` — it's written for both humans and AI agents.
2. Read `docs/ARCHITECTURE.md` — architecture decisions are documented there
   and aren't meant to be relitigated lightly.
3. Don't commit `data/raw/` or `data/parsed/` — they're gitignored and
   scraped data from st-minutiae.com is not ours to redistribute.
4. Don't add DS9/VOY until TNG GraphRAG is validated end-to-end. The graph
   schema will evolve when we do multi-series.
5. Run the test suite: `.venv/bin/python -m pytest tests/`

Ideas especially welcome in: location normalization, behavioral card generation,
and the Episode Writer architecture.

---

## License & Attribution

Code: MIT License — see LICENSE.

**Star Trek IP notice:** Star Trek, The Next Generation, and all character
names are trademarks and copyright of CBS Studios / Paramount Global.
This project is a fan work for educational and research purposes only.
No commercial use. No redistribution of episode scripts.

**Script source:** Episode scripts were scraped from
[st-minutiae.com](https://www.st-minutiae.com/resources/scripts/) with
respect for their terms of service. Do not redistribute the raw `.txt` files.

---

## Built with Hermes Agent

> This project was designed and built interactively with
> **[Hermes Agent](https://hermes-agent.nousresearch.com)** (Nous Research)
> running Claude Opus on Ubuntu Linux (kernel 7.0.0-15-generic).
> The architecture, graph schema, parser, loader, embedder, retriever,
> character agents, and all documentation were generated in a single
> collaborative session. Author: Eric Stewart.

Hermes Agent is an AI agent platform by [Nous Research](https://nousresearch.com)
that lets you work with Claude and other LLMs via a persistent, tool-using agent
session — with file editing, terminal access, and skill memory.
