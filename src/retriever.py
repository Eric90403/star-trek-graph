#!/usr/bin/env python3
"""
src/retriever.py — Phase 2: GraphRAG retrieval for character agents.

Two-phase retrieval:
  1. Vector search: Qdrant semantic search filtered by speaker
  2. Graph expansion: Neo4j hops to pull episode + relationship context

Usage (as a module):
    from retriever import Retriever
    r = Retriever()
    context = r.retrieve("PICARD", "What do you think about the Prime Directive?")
    # context = {lines: [...], graph_context: {...}, prompt_block: "..."}
"""

import os
import sys

# Device detection — handles CUDA (Linux/Windows), MPS (Apple Silicon), CPU fallback.
# This replaces the old hardcoded CUDA_VISIBLE_DEVICES="" override.
sys.path.insert(0, os.path.dirname(__file__))
from device_utils import get_device  # noqa: E402

import warnings
warnings.filterwarnings("ignore")

from neo4j import GraphDatabase
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from sentence_transformers import SentenceTransformer

# ── Config ────────────────────────────────────────────────────────────────────

NEO4J_URI      = "bolt://localhost:7688"
NEO4J_USER     = "neo4j"
NEO4J_PASSWORD = "trekgraph"
QDRANT_URL     = "http://localhost:6333"
COLLECTION     = "trek_lines"
EMBED_MODEL    = "nomic-ai/nomic-embed-text-v1.5"
QUERY_PREFIX   = "search_query: "

DEFAULT_TOP_K  = 40     # lines to retrieve per turn
EXPAND_LIMIT   = 3      # max episodes to expand in graph


# ── Retriever class ───────────────────────────────────────────────────────────

class Retriever:
    def __init__(self):
        print("Loading embedding model...", end=" ", flush=True)
        self.model = SentenceTransformer(EMBED_MODEL, trust_remote_code=True, device=get_device())
        print("done")
        self.qclient = QdrantClient(url=QDRANT_URL)
        self.driver  = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    def close(self):
        self.driver.close()

    # ── Vector search ────────────────────────────────────────────────────────

    def search_lines(self, speaker: str, query: str, top_k: int = DEFAULT_TOP_K,
                     extra_filters: list = None) -> list[dict]:
        """Semantic search over a character's lines, filtered by speaker."""
        vec = self.model.encode(
            [QUERY_PREFIX + query],
            normalize_embeddings=True,
            show_progress_bar=False,
        )[0].tolist()

        must = [FieldCondition(key="speaker", match=MatchValue(value=speaker.upper()))]
        if extra_filters:
            must.extend(extra_filters)

        results = self.qclient.search(
            collection_name=COLLECTION,
            query_vector=vec,
            query_filter=Filter(must=must),
            limit=top_k,
            with_payload=True,
        )
        return [r.payload for r in results]

    # ── Graph expansion ──────────────────────────────────────────────────────

    def expand_episodes(self, episode_ids: list[str], character: str) -> dict:
        """
        Given a set of episode IDs from vector search, pull richer context
        from Neo4j: what else happened, who else was there, relationships.
        """
        with self.driver.session() as s:
            # Episode summaries
            eps = s.run("""
                MATCH (e:Episode)
                WHERE e.id IN $ids
                RETURN e.id AS id, e.title AS title,
                       e.stardate AS stardate, e.writer AS writer
                ORDER BY e.stardate
            """, ids=episode_ids[:EXPAND_LIMIT]).data()

            # Key scene partners in those episodes
            partners = s.run("""
                MATCH (c:Character {canonical_name: $name})<-[:SPOKEN_BY]-(:Line)
                      -[:IN_SCENE]->(s:Scene)-[:IN_EPISODE]->(e:Episode)
                WHERE e.id IN $ids
                MATCH (s)<-[:IN_SCENE]-(:Line)-[:SPOKEN_BY]->(other:Character)
                WHERE other.canonical_name <> $name
                RETURN other.canonical_name AS partner,
                       count(DISTINCT s) AS shared_scenes,
                       e.title AS episode
                ORDER BY shared_scenes DESC LIMIT 10
            """, name=character.upper(), ids=episode_ids[:EXPAND_LIMIT]).data()

            # Overall relationship strength (full corpus)
            relationships = s.run("""
                MATCH (c:Character {canonical_name: $name})<-[:SPOKEN_BY]-(:Line)
                      -[:IN_SCENE]->(s:Scene)<-[:IN_SCENE]-(:Line)
                      -[:SPOKEN_BY]->(other:Character)
                WHERE other.canonical_name <> $name
                RETURN other.canonical_name AS partner,
                       count(DISTINCT s) AS total_shared_scenes
                ORDER BY total_shared_scenes DESC LIMIT 8
            """, name=character.upper()).data()

        return {
            "episodes": eps,
            "scene_partners_in_context": partners,
            "top_relationships": relationships,
        }

    # ── Character card ───────────────────────────────────────────────────────

    def get_character_card(self, character: str) -> dict:
        """Load compact character facts from Neo4j."""
        with self.driver.session() as s:
            char = s.run(
                "MATCH (c:Character {canonical_name: $name}) RETURN c",
                name=character.upper()
            ).single()

            line_count = s.run("""
                MATCH (l:Line)-[:SPOKEN_BY]->(c:Character {canonical_name: $name})
                RETURN count(l) AS n
            """, name=character.upper()).single()["n"]

            episodes = s.run("""
                MATCH (c:Character {canonical_name: $name})-[:APPEARS_IN]->(e:Episode)
                RETURN count(e) AS n
            """, name=character.upper()).single()["n"]

            top_costars = s.run("""
                MATCH (c:Character {canonical_name: $name})<-[:SPOKEN_BY]-(:Line)
                      -[:IN_SCENE]->(s:Scene)<-[:IN_SCENE]-(:Line)
                      -[:SPOKEN_BY]->(other:Character)
                WHERE other.canonical_name <> $name
                WITH other.canonical_name AS costar, count(DISTINCT s) AS scenes
                ORDER BY scenes DESC LIMIT 8
                RETURN collect(costar) AS costars
            """, name=character.upper()).single()["costars"]

        return {
            "canonical_name": character.upper(),
            "properties": dict(char["c"]) if char else {},
            "total_lines": line_count,
            "total_episodes": episodes,
            "top_costars": top_costars,
            "series": "TNG",
        }

    # ── Full retrieval ───────────────────────────────────────────────────────

    def retrieve(self, character: str, query: str,
                 top_k: int = DEFAULT_TOP_K) -> dict:
        """
        Full GraphRAG retrieval. Returns a dict with:
          - lines:         list of retrieved line payloads
          - graph_context: expanded episode + relationship context
          - character_card: compact character facts
          - prompt_block:  pre-formatted string ready for system prompt
        """
        # Phase 1: vector search
        lines = self.search_lines(character, query, top_k=top_k)

        # Phase 2: graph expansion on top episode IDs
        episode_ids = list(dict.fromkeys(l["episode_id"] for l in lines))
        graph_ctx = self.expand_episodes(episode_ids, character)

        # Phase 3: character card
        card = self.get_character_card(character)

        # Assemble prompt block
        prompt_block = _format_prompt_block(character, card, lines, graph_ctx, query)

        return {
            "lines": lines,
            "graph_context": graph_ctx,
            "character_card": card,
            "prompt_block": prompt_block,
        }


# ── Prompt formatting ─────────────────────────────────────────────────────────

def _format_prompt_block(character: str, card: dict, lines: list,
                          graph_ctx: dict, query: str) -> str:
    name = character.title()

    # Character card section
    card_lines = [
        f"CHARACTER: {name}",
        f"Total canon lines: {card['total_lines']:,} across {card['total_episodes']} episodes",
        f"Frequent scene partners: {', '.join(card['top_costars'][:6])}",
    ]
    if card["properties"]:
        for k, v in card["properties"].items():
            if v and k != "canonical_name":
                card_lines.append(f"{k}: {v}")

    # Relationship context
    rel_lines = ["Top relationships (by shared scenes):"]
    for r in graph_ctx["top_relationships"]:
        rel_lines.append(f"  {r['partner']}: {r['total_shared_scenes']} shared scenes")

    # Retrieved dialogue — most relevant to this query
    dialogue_lines = [
        f"\nMOST RELEVANT CANON DIALOGUE ({len(lines)} lines retrieved for this query):",
        "These are the lines most semantically relevant to the current question.",
        "Draw your voice and answers from these records.\n",
    ]
    current_ep = None
    for l in lines:
        if l["episode_title"] != current_ep:
            current_ep = l["episode_title"]
            dialogue_lines.append(f"\n[{current_ep}]")
        paren = f" ({l['parenthetical']})" if l.get("parenthetical") else ""
        others = f"  [scene also has: {', '.join(l['other_speakers'][:4])}]" \
                 if l.get("other_speakers") else ""
        dialogue_lines.append(f"  {name.upper()}{paren}: {l['text']}{others}")

    return "\n".join(card_lines + [""] + rel_lines + dialogue_lines)


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    character = sys.argv[1] if len(sys.argv) > 1 else "PICARD"
    query     = " ".join(sys.argv[2:]) if len(sys.argv) > 2 \
                else "What do you think about duty and sacrifice?"

    print(f"\nGraphRAG retrieval: {character} | '{query}'\n")
    r = Retriever()
    ctx = r.retrieve(character, query, top_k=20)
    r.close()

    print(ctx["prompt_block"])
    print(f"\n--- {len(ctx['lines'])} lines retrieved ---")
    print(f"--- {len(ctx['graph_context']['episodes'])} episodes expanded ---")
