#!/usr/bin/env python3
"""
src/embedder.py — Embed all canon lines into Qdrant with graph metadata.

Pulls every Line from Neo4j with its graph context (speaker, episode, scene,
location, co-present characters), embeds the text with a local sentence
transformer, and pushes each point — vector + full metadata payload — into
Qdrant. This is the foundation of GraphRAG retrieval at query time.

Safe to re-run: point IDs are deterministic (sha1 of line_id), so upserts
update existing points in place rather than creating duplicates.

Usage:
    python src/embedder.py                    # embed everything
    python src/embedder.py --dry-run          # count lines, no embedding
    python src/embedder.py --batch-size 128   # tune for your CPU/GPU
    python src/embedder.py --speaker PICARD   # embed one character only
    python src/embedder.py --reset            # drop and recreate the collection
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import time
import warnings

warnings.filterwarnings("ignore")

# Local imports — make src/ importable
sys.path.insert(0, os.path.dirname(__file__))
from device_utils import get_device                                  # noqa: E402
from config import (                                                 # noqa: E402
    NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD,
    QDRANT_URL, QDRANT_COLLECTION,
    EMBED_MODEL, EMBED_DIM, DOC_PREFIX,
)

from neo4j import GraphDatabase                                       # noqa: E402
from qdrant_client import QdrantClient                                # noqa: E402
from qdrant_client.models import (                                    # noqa: E402
    Distance, VectorParams, PointStruct, OptimizersConfigDiff,
)
from sentence_transformers import SentenceTransformer                 # noqa: E402
from tqdm import tqdm                                                 # noqa: E402

# ── The enrichment query ──────────────────────────────────────────────────────
# Each vector point carries full graph metadata as payload so Qdrant can
# do filtered semantic search (e.g. "Picard lines from scenes with Worf").

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
    l.id                          AS line_id,
    l.text                        AS text,
    l.parenthetical               AS parenthetical,
    speaker.canonical_name        AS speaker,
    e.id                          AS episode_id,
    e.title                       AS episode_title,
    e.stardate                    AS stardate,
    e.canon_tier                  AS canon_tier,
    coalesce(e.series, 'UNKNOWN') AS series,
    s.scene_num                   AS scene_num,
    coalesce(loc.name, 'UNKNOWN') AS location,
    others                        AS other_speakers
ORDER BY e.id, s.scene_num, l.id
"""

SPEAKER_FILTER_CYPHER = ENRICHMENT_CYPHER.replace(
    "WHERE size(l.text) > 3",
    "WHERE size(l.text) > 3 AND speaker.canonical_name = $speaker",
)

SERIES_FILTER_CYPHER = ENRICHMENT_CYPHER.replace(
    "WHERE size(l.text) > 3",
    "WHERE size(l.text) > 3 AND e.series = $series",
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_neo4j_lines(driver, speaker: str | None = None,
                    series: str | None = None) -> list[dict]:
    """Pull all lines with graph metadata, optionally filtered by speaker or series."""
    with driver.session() as session:
        if speaker:
            result = session.run(SPEAKER_FILTER_CYPHER, speaker=speaker.upper())
        elif series:
            result = session.run(SERIES_FILTER_CYPHER, series=series.upper())
        else:
            result = session.run(ENRICHMENT_CYPHER)
        return result.data()


def ensure_collection(qclient: QdrantClient, reset: bool = False) -> None:
    """Create the Qdrant collection if it does not exist; optionally reset it."""
    existing = {c.name for c in qclient.get_collections().collections}

    if reset and QDRANT_COLLECTION in existing:
        qclient.delete_collection(QDRANT_COLLECTION)
        existing.discard(QDRANT_COLLECTION)
        print(f"Dropped existing collection '{QDRANT_COLLECTION}'")

    if QDRANT_COLLECTION not in existing:
        qclient.create_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
            optimizers_config=OptimizersConfigDiff(indexing_threshold=20000),
        )
        print(f"Created Qdrant collection '{QDRANT_COLLECTION}' "
              f"(dim={EMBED_DIM}, distance=cosine)")
    else:
        count = qclient.count(QDRANT_COLLECTION).count
        print(f"Collection '{QDRANT_COLLECTION}' exists with {count:,} points")


def make_point_id(line_id: str) -> int:
    """
    Stable 63-bit integer ID for Qdrant, derived from line_id.

    IMPORTANT: must NOT use Python's built-in hash() — it is randomised per
    process via PYTHONHASHSEED, so the same line would get a different ID
    on every run, corrupting the collection with duplicates.
    """
    digest = hashlib.sha1(line_id.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & ((1 << 63) - 1)


def row_to_payload(row: dict) -> dict:
    """Build the Qdrant point payload from a Neo4j enrichment row."""
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
        "series":         row.get("series") or "UNKNOWN",
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def embed_and_load(args: argparse.Namespace) -> int:
    print("\n══ EMBED + LOAD TO QDRANT ═══════════════════════════")

    # 1. Pull lines from Neo4j
    print("Connecting to Neo4j...")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    speaker_note = ""
    if args.speaker:
        speaker_note = f" (speaker={args.speaker})"
    elif args.series:
        speaker_note = f" (series={args.series})"
    print(f"Pulling lines from graph{speaker_note}...")
    t0 = time.time()
    rows = get_neo4j_lines(driver, speaker=args.speaker, series=args.series)
    driver.close()
    print(f"  {len(rows):,} lines retrieved in {time.time() - t0:.1f}s")

    if not rows:
        print("\nNo lines found. Did you run scripts/ingest_tng.py first?")
        return 1

    if args.dry_run:
        from collections import Counter
        print("\nDry run — not embedding. Top speakers in result set:")
        counts = Counter(r["speaker"] for r in rows)
        for name, n in counts.most_common(15):
            print(f"  {name:<22} {n:>6,}")
        return 0

    # 2. Load embedding model
    print(f"\nLoading {EMBED_MODEL}...")
    t1 = time.time()
    model = SentenceTransformer(EMBED_MODEL, trust_remote_code=True,
                                device=get_device())
    print(f"  Model loaded in {time.time() - t1:.1f}s")

    # 3. Connect to Qdrant and ensure collection exists
    print("\nConnecting to Qdrant...")
    qclient = QdrantClient(url=QDRANT_URL)
    ensure_collection(qclient, reset=args.reset)

    # 4. Embed and upsert in batches
    batch_size = args.batch_size
    total = len(rows)
    print(f"\nEmbedding {total:,} lines in batches of {batch_size}...")
    print(f"  Prefix:  '{DOC_PREFIX}[text]'")
    print(f"  Hash:    sha1 (deterministic — re-runs upsert in place)\n")

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
            qclient.upsert(collection_name=QDRANT_COLLECTION,
                           points=points, wait=False)
            upserted += len(points)
        except Exception as exc:
            errors += len(batch)
            print(f"\n  ERROR at batch {i // batch_size}: {exc}")

    elapsed = time.time() - t2
    rate = total / elapsed if elapsed > 0 else 0
    print("\nEmbedding complete:")
    print(f"  {upserted:,} points upserted to '{QDRANT_COLLECTION}'")
    print(f"  {errors:,} errors")
    print(f"  {elapsed:.1f}s total  ({rate:.0f} lines/sec)")

    # 5. Final count (let Qdrant settle async writes)
    time.sleep(2)
    final_count = qclient.count(QDRANT_COLLECTION).count
    print(f"  Qdrant collection count: {final_count:,}")

    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Embed canon lines into Qdrant")
    ap.add_argument("--dry-run",    action="store_true",
                    help="Count lines only, no embedding")
    ap.add_argument("--speaker",    type=str, default=None,
                    help="Embed one speaker only (e.g. PICARD)")
    ap.add_argument("--series",     type=str, default=None,
                    help="Embed one series only (e.g. TNG, TOS)")
    ap.add_argument("--batch-size", type=int, default=64,
                    help="Embedding batch size (default 64)")
    ap.add_argument("--reset",      action="store_true",
                    help="Drop and recreate the collection before embedding")
    return embed_and_load(ap.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
