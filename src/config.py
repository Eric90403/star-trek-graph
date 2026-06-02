"""
src/config.py — Centralised configuration with environment-variable support.

All connection strings, credentials, and tunables live here. Override any of
them with environment variables before launching scripts. Defaults match the
project's docker-compose.yml.

Example:
    export TREK_NEO4J_URI=bolt://staging-host:7687
    export TREK_QDRANT_URL=http://localhost:6334
    ./trek
"""

from __future__ import annotations

import os

# ── Version ───────────────────────────────────────────────────────────────────

__version__ = "0.2.0"

# ── Neo4j ─────────────────────────────────────────────────────────────────────

NEO4J_URI      = os.environ.get("TREK_NEO4J_URI",      "bolt://localhost:7688")
NEO4J_USER     = os.environ.get("TREK_NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.environ.get("TREK_NEO4J_PASSWORD", "trekgraph")

# ── Qdrant ────────────────────────────────────────────────────────────────────

QDRANT_URL        = os.environ.get("TREK_QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = os.environ.get("TREK_QDRANT_COLLECTION", "trek_lines")

# ── Embedding model ───────────────────────────────────────────────────────────

EMBED_MODEL  = os.environ.get("TREK_EMBED_MODEL", "nomic-ai/nomic-embed-text-v1.5")
EMBED_DIM    = int(os.environ.get("TREK_EMBED_DIM", "768"))
DOC_PREFIX   = "search_document: "    # required by nomic-embed-text-v1.5
QUERY_PREFIX = "search_query: "       # required by nomic-embed-text-v1.5

# ── LLM ───────────────────────────────────────────────────────────────────────

# Anthropic model used by character_agent. Override with --model on CLI or env.
DEFAULT_LLM_MODEL = os.environ.get("TREK_LLM_MODEL", "claude-opus-4-5")

# ── Retrieval defaults ────────────────────────────────────────────────────────

DEFAULT_TOP_K       = int(os.environ.get("TREK_TOP_K", "40"))
EXPAND_LIMIT        = int(os.environ.get("TREK_EXPAND_LIMIT", "3"))
HISTORY_TURNS_KEPT  = int(os.environ.get("TREK_HISTORY_TURNS", "10"))
MAX_OUTPUT_TOKENS   = int(os.environ.get("TREK_MAX_OUTPUT_TOKENS", "1024"))
