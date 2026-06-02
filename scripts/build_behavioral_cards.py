#!/usr/bin/env python3
"""
scripts/build_behavioral_cards.py — Phase 3 orchestrator.

Builds BehavioralCard nodes for the top-N characters by line count.
Idempotent: skips characters whose cards already exist unless --rebuild.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from neo4j import GraphDatabase                                       # noqa: E402
from config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD              # noqa: E402
from auth import get_anthropic_client                                 # noqa: E402
from behavioral_extractor import (                                    # noqa: E402
    get_top_characters,
    sample_lines_for_character,
    extract_behavioral_card,
    store_behavioral_card,
    card_exists,
    ensure_schema,
)

BACKUP_DIR = ROOT / "data" / "behavioral_cards"
MODEL = "claude-sonnet-4-5"

# Anthropic Sonnet 4.5 pricing (USD per 1M tokens), as of 2025-2026:
# input $3.00, output $15.00. Update if pricing changes.
PRICE_IN_PER_M  = 3.00
PRICE_OUT_PER_M = 15.00


def estimate_cost(in_tok: int, out_tok: int) -> float:
    return (in_tok / 1_000_000) * PRICE_IN_PER_M + (out_tok / 1_000_000) * PRICE_OUT_PER_M


def main() -> int:
    ap = argparse.ArgumentParser(description="Build Layer 2 BehavioralCards.")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--rebuild", action="store_true",
                    help="Re-extract even if a card already exists.")
    ap.add_argument("--character", type=str, default=None,
                    help="Process only this single canonical_name.")
    ap.add_argument("--sample-size", type=int, default=200)
    ap.add_argument("--model", type=str, default=MODEL)
    args = ap.parse_args()

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    # Ensure data/behavioral_cards is gitignored
    gi = ROOT / ".gitignore"
    if gi.exists():
        gi_text = gi.read_text()
        if "data/behavioral_cards" not in gi_text:
            with gi.open("a") as f:
                f.write("\ndata/behavioral_cards/\n")

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    ensure_schema(driver)
    client = get_anthropic_client()

    if args.character:
        # Pull just metadata for one character
        tops = [t for t in get_top_characters(driver, limit=200)
                if t["canonical_name"] == args.character]
        if not tops:
            print(f"Character {args.character!r} not found in top 200.")
            return 1
    else:
        tops = get_top_characters(driver, limit=args.limit)

    print(f"Targets ({len(tops)}):")
    for t in tops:
        print(f"  {t['canonical_name']:<10} lines={t['total_lines']:>6}  {t['series_breakdown']}")
    print()

    total_in = 0
    total_out = 0
    built = 0
    skipped = 0
    failures: list[tuple[str, str]] = []

    for t in tops:
        name = t["canonical_name"]
        if card_exists(driver, name) and not args.rebuild:
            print(f"[skip] {name}: card exists")
            skipped += 1
            continue
        print(f"[work] {name}: sampling...", flush=True)
        t0 = time.time()
        try:
            lines = sample_lines_for_character(driver, name, sample_size=args.sample_size)
            if not lines:
                print(f"  no lines found, skipping")
                failures.append((name, "no lines"))
                continue
            print(f"  sampled {len(lines)} lines; calling {args.model}...", flush=True)
            card, usage = extract_behavioral_card(client, name, lines, model=args.model)
            total_in  += usage["input_tokens"]
            total_out += usage["output_tokens"]
            store_behavioral_card(driver, card)
            backup = BACKUP_DIR / f"{name}.json"
            backup.write_text(json.dumps(card, indent=2))
            dt = time.time() - t0
            print(f"  ✓ stored ({usage['input_tokens']}/{usage['output_tokens']} tok, {dt:.1f}s)")
            built += 1
        except Exception as e:
            print(f"  ✗ FAILED: {e}")
            failures.append((name, str(e)[:200]))

    cost = estimate_cost(total_in, total_out)
    print()
    print("=" * 60)
    print(f"Built:    {built}")
    print(f"Skipped:  {skipped}")
    print(f"Failed:   {len(failures)}")
    print(f"Tokens:   input={total_in:,}  output={total_out:,}")
    print(f"Est cost: ${cost:.4f}  (sonnet-4.5 @ ${PRICE_IN_PER_M}/${PRICE_OUT_PER_M} per M)")
    if failures:
        print("\nFailures:")
        for n, e in failures:
            print(f"  {n}: {e}")

    # Verify
    with driver.session() as s:
        n = s.run(
            "MATCH (c:Character)-[:HAS_BEHAVIORAL_CARD]->(b:BehavioralCard) "
            "RETURN count(DISTINCT c) AS chars, count(b) AS cards"
        ).single()
        print(f"\nNeo4j verification: {n['chars']} Characters with {n['cards']} BehavioralCards")

    driver.close()
    return 0 if not failures else 2


if __name__ == "__main__":
    sys.exit(main())
