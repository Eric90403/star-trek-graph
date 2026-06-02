#!/usr/bin/env python3
"""
src/retriever.py — GraphRAG retrieval for character agents.

Two-phase retrieval:
  1. Vector search: Qdrant semantic search filtered by speaker
  2. Graph expansion: Neo4j hops to pull episode + relationship context

Usage (as a module):
    from retriever import Retriever
    r = Retriever()
    ctx = r.retrieve("PICARD", "What do you think about the Prime Directive?")
    print(ctx["prompt_block"])     # ready to paste into a system prompt
"""

from __future__ import annotations

import os
import sys
import warnings

warnings.filterwarnings("ignore")

# Local imports
sys.path.insert(0, os.path.dirname(__file__))
from device_utils import get_device                                  # noqa: E402
from config import (                                                 # noqa: E402
    NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD,
    QDRANT_URL, QDRANT_COLLECTION,
    EMBED_MODEL, QUERY_PREFIX,
    DEFAULT_TOP_K, EXPAND_LIMIT,
)

from neo4j import GraphDatabase                                       # noqa: E402
from qdrant_client import QdrantClient                                # noqa: E402
from qdrant_client.models import Filter, FieldCondition, MatchValue   # noqa: E402
from sentence_transformers import SentenceTransformer                 # noqa: E402


# ── Exceptions ────────────────────────────────────────────────────────────────

class EmptyCollectionError(RuntimeError):
    """Raised when Qdrant has no points to retrieve from — usually means
    the user has not yet run scripts/ingest_tng.py followed by src/embedder.py.
    """


# ── Retriever ─────────────────────────────────────────────────────────────────

class Retriever:
    """Encapsulates the full GraphRAG retrieval stack: embedder, vector DB,
    graph DB. Construct once per process, reuse across many queries."""

    def __init__(self) -> None:
        print("Loading embedding model...", end=" ", flush=True)
        self.model = SentenceTransformer(
            EMBED_MODEL, trust_remote_code=True, device=get_device()
        )
        print("done")
        self.qclient = QdrantClient(url=QDRANT_URL)
        self.driver = GraphDatabase.driver(
            NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
        )
        self._check_collection()

    def close(self) -> None:
        self.driver.close()

    def _check_collection(self) -> None:
        """Verify the Qdrant collection exists and has points. Fail fast
        with a helpful message if either is wrong."""
        try:
            count = self.qclient.count(QDRANT_COLLECTION, exact=False).count
        except Exception as exc:
            raise EmptyCollectionError(
                f"\nQdrant collection '{QDRANT_COLLECTION}' is not reachable.\n"
                f"  - Is the Qdrant container running? (docker ps | grep qdrant)\n"
                f"  - Have you run the embedder? (python src/embedder.py)\n"
                f"  - Original error: {exc}"
            ) from exc

        if count == 0:
            raise EmptyCollectionError(
                f"\nQdrant collection '{QDRANT_COLLECTION}' exists but is empty.\n"
                f"  Build the embeddings first:\n"
                f"    python src/embedder.py\n"
            )

    # ── Vector search ────────────────────────────────────────────────────────

    def search_lines(self, speaker: str, query: str,
                     top_k: int = DEFAULT_TOP_K,
                     series: str | None = None) -> list[dict]:
        """Semantic search over a character's lines, filtered by speaker.

        Optional `series` filter restricts results to one show (e.g. "TNG",
        "TOS"). Useful for characters that appear in multiple series — but
        for now Kirk/Spock/McCoy are TOS-only, Picard is TNG-only, etc.
        """
        vec = self.model.encode(
            [QUERY_PREFIX + query],
            normalize_embeddings=True,
            show_progress_bar=False,
        )[0].tolist()

        must = [FieldCondition(key="speaker",
                               match=MatchValue(value=speaker.upper()))]
        if series:
            must.append(FieldCondition(key="series",
                                       match=MatchValue(value=series.upper())))

        # query_points is the modern API; search() is deprecated in 1.18+
        result = self.qclient.query_points(
            collection_name=QDRANT_COLLECTION,
            query=vec,
            query_filter=Filter(must=must),
            limit=top_k,
            with_payload=True,
        )
        return [p.payload for p in result.points]

    # ── Graph expansion ──────────────────────────────────────────────────────

    def expand_episodes(self, episode_ids: list[str], character: str) -> dict:
        """Pull richer context from Neo4j for the top retrieved episodes."""
        ids = episode_ids[:EXPAND_LIMIT]
        name = character.upper()

        with self.driver.session() as session:
            episodes = session.run("""
                MATCH (e:Episode)
                WHERE e.id IN $ids
                RETURN e.id AS id, e.title AS title,
                       e.stardate AS stardate, e.writer AS writer
                ORDER BY e.stardate
            """, ids=ids).data()

            partners = session.run("""
                MATCH (c:Character {canonical_name: $name})<-[:SPOKEN_BY]-(:Line)
                      -[:IN_SCENE]->(s:Scene)-[:IN_EPISODE]->(e:Episode)
                WHERE e.id IN $ids
                MATCH (s)<-[:IN_SCENE]-(:Line)-[:SPOKEN_BY]->(other:Character)
                WHERE other.canonical_name <> $name
                RETURN other.canonical_name AS partner,
                       count(DISTINCT s)    AS shared_scenes,
                       e.title              AS episode
                ORDER BY shared_scenes DESC LIMIT 10
            """, name=name, ids=ids).data()

            relationships = session.run("""
                MATCH (c:Character {canonical_name: $name})<-[:SPOKEN_BY]-(:Line)
                      -[:IN_SCENE]->(s:Scene)<-[:IN_SCENE]-(:Line)
                      -[:SPOKEN_BY]->(other:Character)
                WHERE other.canonical_name <> $name
                RETURN other.canonical_name AS partner,
                       count(DISTINCT s)    AS total_shared_scenes
                ORDER BY total_shared_scenes DESC LIMIT 8
            """, name=name).data()

        return {
            "episodes":                  episodes,
            "scene_partners_in_context": partners,
            "top_relationships":         relationships,
        }

    # ── Character card ───────────────────────────────────────────────────────

    def get_character_card(self, character: str) -> dict:
        """Compact, mostly-static facts about a character — loaded once.

        Includes the BehavioralCard (Layer 2) if one exists.
        """
        name = character.upper()
        with self.driver.session() as session:
            char_node = session.run(
                "MATCH (c:Character {canonical_name: $name}) RETURN c",
                name=name,
            ).single()

            stats = session.run("""
                MATCH (c:Character {canonical_name: $name})
                OPTIONAL MATCH (l:Line)-[:SPOKEN_BY]->(c)
                WITH c, count(l) AS line_count
                OPTIONAL MATCH (c)-[:APPEARS_IN]->(e:Episode)
                RETURN line_count,
                       count(DISTINCT e) AS episode_count
            """, name=name).single()

            costars = session.run("""
                MATCH (c:Character {canonical_name: $name})<-[:SPOKEN_BY]-(:Line)
                      -[:IN_SCENE]->(s:Scene)<-[:IN_SCENE]-(:Line)
                      -[:SPOKEN_BY]->(other:Character)
                WHERE other.canonical_name <> $name
                WITH other.canonical_name AS costar, count(DISTINCT s) AS scenes
                ORDER BY scenes DESC LIMIT 8
                RETURN collect(costar) AS costars
            """, name=name).single()

            behavioral_card = session.run("""
                MATCH (c:Character {canonical_name: $name})
                      -[:HAS_BEHAVIORAL_CARD]->(bc:BehavioralCard)
                RETURN bc
            """, name=name).single()

        bc = dict(behavioral_card["bc"]) if behavioral_card else {}

        return {
            "canonical_name":   name,
            "properties":       dict(char_node["c"]) if char_node else {},
            "total_lines":      (stats["line_count"]    if stats else 0) or 0,
            "total_episodes":   (stats["episode_count"] if stats else 0) or 0,
            "top_costars":      (costars["costars"] if costars else []) or [],
            "behavioral_card":  bc,
            "series":           "TNG",
        }

    # ── Full retrieval ───────────────────────────────────────────────────────

    def retrieve(self, character: str, query: str,
                 top_k: int = DEFAULT_TOP_K,
                 series: str | None = None) -> dict:
        """Return retrieved lines, graph context, character card, and a
        ready-to-use prompt_block string for the agent's system prompt.

        If `series` is provided (e.g. "TNG", "TOS"), retrieval is scoped
        to lines from that series only."""
        lines = self.search_lines(character, query, top_k=top_k, series=series)
        episode_ids = list(dict.fromkeys(l["episode_id"] for l in lines))
        graph_ctx = self.expand_episodes(episode_ids, character)
        card = self.get_character_card(character)
        prompt_block = _format_prompt_block(character, card, lines, graph_ctx)

        return {
            "lines":          lines,
            "graph_context":  graph_ctx,
            "character_card": card,
            "prompt_block":   prompt_block,
        }


# ── Prompt formatting ─────────────────────────────────────────────────────────

def _format_prompt_block(character: str, card: dict,
                          lines: list, graph_ctx: dict) -> str:
    name = character.title()

    card_lines = [
        f"CHARACTER: {name}",
        f"Total canon lines: {card['total_lines']:,} "
        f"across {card['total_episodes']} episodes",
        f"Frequent scene partners: "
        f"{', '.join(card['top_costars'][:6]) or '(none recorded)'}",
    ]
    for k, v in (card.get("properties") or {}).items():
        if v and k != "canonical_name":
            card_lines.append(f"{k}: {v}")

    # Behavioral card (Layer 2) — if present, this is the main voice driver
    bc = card.get("behavioral_card") or {}
    bc_lines: list[str] = []
    if bc:
        import json as _json

        def _decode(field: str) -> list:
            # Card list-fields are stored as `<field>_json` (JSON-encoded strings)
            v = bc.get(field + "_json") or bc.get(field, "")
            if not v:
                return []
            try:
                return _json.loads(v) if isinstance(v, str) else list(v)
            except Exception:
                return [v]

        bc_lines.append("")
        bc_lines.append("BEHAVIORAL PROFILE (derived from your own dialogue):")
        if bc.get("core_identity"):
            bc_lines.append(f"\nCore identity: {bc['core_identity']}")
        if bc.get("driving_question"):
            bc_lines.append(f"\nDriving question: {bc['driving_question']}")

        for label, field in [
            ("Speech patterns",     "speech_patterns"),
            ("Decision heuristics", "decision_heuristics"),
            ("Hard limits",         "hard_limits"),
        ]:
            items = _decode(field)
            if items:
                bc_lines.append(f"\n{label}:")
                for it in items:
                    bc_lines.append(f"  • {it}")

        sigs = _decode("signature_phrases")
        if sigs:
            bc_lines.append(f"\nSignature phrases: " +
                            ", ".join(f'"{s}"' for s in sigs[:12]))

        if bc.get("emotional_range"):
            bc_lines.append(f"\nEmotional range: {bc['emotional_range']}")
        if bc.get("intellectual_style"):
            bc_lines.append(f"\nIntellectual style: {bc['intellectual_style']}")

    rel_lines = ["", "Top relationships (by shared scenes):"]
    for r in graph_ctx["top_relationships"]:
        rel_lines.append(f"  {r['partner']}: {r['total_shared_scenes']} shared scenes")

    dialogue_lines = [
        "",
        f"MOST RELEVANT CANON DIALOGUE ({len(lines)} lines retrieved):",
        "These are the lines most semantically relevant to the current question.",
        "Draw your voice and answers from these records.",
        "",
    ]
    current_ep = None
    for l in lines:
        if l["episode_title"] != current_ep:
            current_ep = l["episode_title"]
            dialogue_lines.append(f"\n[{current_ep}]")
        paren = f" ({l['parenthetical']})" if l.get("parenthetical") else ""
        others = (f"  [scene also has: {', '.join(l['other_speakers'][:4])}]"
                  if l.get("other_speakers") else "")
        dialogue_lines.append(f"  {name.upper()}{paren}: {l['text']}{others}")

    return "\n".join(card_lines + bc_lines + rel_lines + dialogue_lines)


# ── CLI smoke test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    character = sys.argv[1] if len(sys.argv) > 1 else "PICARD"
    query = (" ".join(sys.argv[2:])
             if len(sys.argv) > 2
             else "What do you think about duty and sacrifice?")

    print(f"\nGraphRAG retrieval: {character} | '{query}'\n")
    r = Retriever()
    try:
        ctx = r.retrieve(character, query, top_k=20)
        print(ctx["prompt_block"])
        print(f"\n--- {len(ctx['lines'])} lines retrieved ---")
        print(f"--- {len(ctx['graph_context']['episodes'])} episodes expanded ---")
    finally:
        r.close()
