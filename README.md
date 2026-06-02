# Star Trek Graph

A generative knowledge graph of the Star Trek canon — characters, ships, episodes,
species, tropes, and behavioral models — backed by Neo4j + Qdrant. Powers:

1. **Character chatbots** with RAG-grounded persona fidelity
2. **An Episode Writer** multi-agent harness that generates canon-consistent new episodes
3. **Canon validation** queries for fan-fiction and analysis

## Status

Phase 1 spike: parse 5 TNG scripts, load into Neo4j, validate the schema.

## Quick Start

```bash
# Bring up the database
docker compose up -d

# Open the Neo4j browser
xdg-open http://localhost:7475
# Login: neo4j / trekgraph

# Run the parser + loader
./scripts/spike.sh
```

## Architecture

See `docs/PLAN.md` for the full design and `docs/ONTOLOGY.md` for the
five-layer graph schema (Facts, Behavior, Narrative, Rules, Tone).

## License & Attribution

Code: MIT. Scripts and Star Trek IP belong to CBS/Paramount. This is a
non-commercial, transformative fan/research project. Scripts are sourced
from [st-minutiae.com](https://www.st-minutiae.com/resources/scripts/).
