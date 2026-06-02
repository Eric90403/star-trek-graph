#!/usr/bin/env python3
"""
src/embedder.py — Phase 2: Embed all TNG lines into Qdrant.

Pulls every Line from Neo4j with its graph metadata (speaker, episode,
scene, location, co-present characters), embeds with nomic-embed-text-v1.5,
and pushes to Qdrant collection "trek_lines".

Safe to re-run: uses upsert, checks existing count first.

Usage:
    python src/embedder.py                    # embed everything
    python src/embedder.py --dry-run          # count lines, no embedding
    python src/embedder.py --batch-size 128   # tune for your CPU
    python src/embedder.py --speaker PICARD   # embed one character only
"""

import argparse
import time
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
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, OptimizersConfigDiff
)
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

# ── Config ────────────────────────────────────────────────────────────────────

NEO4J_URI       = "bolt://localhost:7688"
NEO4J_USER      = "neo4j"
NEO4J_PASSWORD  = "trekgraph"

QDRANT_URL      = "http://localhost:6333"
COLLECTION      = "trek_lines"
VECTOR_DIM      = 768           # nomic-embed-text-v1.5 output dims
EMBED_MODEL     = "nomic-ai/nomic-embed-text-v1.5"
DOC_PREFIX      = "search_document: "

# ── The enrichment query ──────────────────────────────────────────────────────
# This is the core of GraphRAG: each vector point carries full graph metadata
# as payload, enabling filtered semantic search at query time.

ENRICHMENT_CYPHER = """
MATCH (l:Line)-[:SPOKEN_BY]->(speaker:Character)
MATCH (l)-[:IN_SCENE]->(s:Scene)-[:IN_EPISODE]->(e:Episode)
OPTIONAL MATCH (s)-[:SET_AT]->(loc:Location)
OPTIONAL MATCH (s)<-[:IN_SCENE]-(:Line)-[:SPOKEN_BY]->(other:Character)
WHERE other.canonical_name <> speaker.canonical_name

WITH l, speaker, s, e, loc,
     collect(DISTINCT other.canonical_name) AS others

WHERE size(l.text) > 3

RETURN
    l.id                        AS line_id,
    l.text                      AS text,
    l.parenthetical             AS parenthetical,
    speaker.canonical_name      AS speaker,
    e.id                        AS episode_id,
    e.title                     AS episode_title,
    e.stardate                  AS stardate,
    e.canon_tier                AS canon_tier,
    s.scene_num                 AS scene_num,
    coalesce(loc.name, 'UNKNOWN') AS location,
    others                      AS other_speakers

ORDER BY e.id, s.scene_num, l.id
"""

SPEAKER_FILTER_CYPHER = ENRICHMENT_CYPHER.replace(
    "WHERE size(l.text) > 3",
    "WHERE size(l.text) > 3 AND speaker.canonical_name = $speaker"
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_neo4j_lines(driver, speaker=None):
    """Pull all lines with graph metadata. Returns list of dicts."""
    with driver.session() as s:
        if speaker:
            result = s.run(SPEAKER_FILTER_CYPHER, speaker=speaker.upper())
        else:
            result = s.run(ENRICHMENT_CYPHER)
        return result.data()


def ensure_collection(qclient):
    """Create trek_lines collection if it doesn't exist."""
    existing = [c.name for c in qclient.get_collections().collections]
    if COLLECTION not in existing:
        qclient.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
            optimizers_config=OptimizersConfigDiff(indexing_threshold=20000),
        )
        print(f"Created Qdrant collection '{COLLECTION}'")
    else:
        count = qclient.count(COLLECTION).count
        print(f"Collection '{COLLECTION}' exists with {count:,} points")


def make_point_id(line_id: str) -> int:
    """Convert line ID string to stable integer for Qdrant."""
    # line IDs look like "line:102:5" — hash to stable int
    return abs(hash(line_id)) % (2**53)


def row_to_payload(row: dict) -> dict:
    """Build Qdrant payload from Neo4j row."""
    return {
        "neo4j_line_id":  row["line_id"],
        "text":           row["text"],
        "parenthetical":  row.get("parenthetical") or "",
        "speaker":        row["speaker"],
        "episode_id":     row["episode_id"],
        "episode_title":  row["episode_title"] or "",
        "stardate":       row["stardate"] or "",
        "canon_tier":     row.get("canon_tier") or 1,
        "scene_num":      row["scene_num"],
        "location":       row["location"],
        "other_speakers": row["other_speakers"] or [],
        "series":         "TNG",
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def embed_and_load(args):
    print("\n══ PHASE 2: EMBED + LOAD TO QDRANT ══════════════════")

    # 1. Pull lines from Neo4j
    print("Connecting to Neo4j...")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    print(f"Pulling lines from graph{f' (speaker={args.speaker})' if args.speaker else ''}...")
    t0 = time.time()
    rows = get_neo4j_lines(driver, speaker=args.speaker)
    driver.close()
    print(f"  {len(rows):,} lines retrieved in {time.time()-t0:.1f}s")

    if args.dry_run:
        print("\nDry run — not embedding. Top speakers:")
        from collections import Counter
        counts = Counter(r["speaker"] for r in rows)
        for name, n in counts.most_common(15):
            print(f"  {name:<22} {n:>6,}")
        return

    # 2. Load embedding model
    print(f"\nLoading {EMBED_MODEL}...")
    t1 = time.time()
    model = SentenceTransformer(EMBED_MODEL, trust_remote_code=True, device=get_device())
    print(f"  Model loaded in {time.time()-t1:.1f}s")

    # 3. Ensure Qdrant collection exists
    print("\nConnecting to Qdrant...")
    qclient = QdrantClient(url=QDRANT_URL)
    ensure_collection(qclient)

    # 4. Embed and upsert in batches
    batch_size = args.batch_size
    total = len(rows)
    print(f"\nEmbedding {total:,} lines in batches of {batch_size}...")
    print(f"  Prefix: '{DOC_PREFIX}[text]'")

    t2 = time.time()
    upserted = 0
    errors = 0

    for i in tqdm(range(0, total, batch_size), desc="Embedding", unit="batch"):
        batch = rows[i : i + batch_size]
        texts = [DOC_PREFIX + r["text"] for r in batch]

        try:
            vecs = model.encode(
                texts,
                batch_size=batch_size,
                show_progress_bar=False,
                normalize_embeddings=True,
            )

            points = [
                PointStruct(
                    id=make_point_id(r["line_id"]),
                    vector=vecs[j].tolist(),
                    payload=row_to_payload(r),
                )
                for j, r in enumerate(batch)
            ]

            qclient.upsert(collection_name=COLLECTION, points=points, wait=False)
            upserted += len(points)

        except Exception as e:
            errors += len(batch)
            print(f"\n  ERROR at batch {i//batch_size}: {e}")

    elapsed = time.time() - t2
    rate = total / elapsed if elapsed > 0 else 0
    print(f"\nEmbedding complete:")
    print(f"  {upserted:,} points upserted to '{COLLECTION}'")
    print(f"  {errors:,} errors")
    print(f"  {elapsed:.1f}s total  ({rate:.0f} lines/sec)")

    # 5. Final count
    time.sleep(2)  # let Qdrant finish async writes
    final_count = qclient.count(COLLECTION).count
    print(f"  Qdrant collection count: {final_count:,}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Embed TNG lines into Qdrant")
    ap.add_argument("--dry-run",    action="store_true", help="Count lines only, no embedding")
    ap.add_argument("--speaker",    type=str, default=None, help="Embed one speaker only")
    ap.add_argument("--batch-size", type=int, default=64,   help="Embedding batch size (default 64)")
    args = ap.parse_args()
    embed_and_load(args)
