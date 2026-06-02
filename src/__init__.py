"""Star Trek Graph — a generative knowledge graph of Star Trek canon.

See README.md for an overview. The main entry points are:

  - scripts/ingest_tng.py    — populate Neo4j from raw scripts
  - src/embedder.py          — build the Qdrant vector index
  - src/character_agent.py   — the GraphRAG character chatbot
"""

from .config import __version__

__all__ = ["__version__"]
