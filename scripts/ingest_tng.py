#!/usr/bin/env python3
"""
Full TNG ingest: fetch all 176 scripts, parse, load into Neo4j.
Safe to re-run: skips already-fetched files, uses MERGE in Neo4j.

Usage:
    python scripts/ingest_tng.py              # full run
    python scripts/ingest_tng.py --parse-only # skip fetch, re-parse existing raw files
    python scripts/ingest_tng.py --load-only  # skip fetch+parse, reload existing JSONs
"""

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

ROOT     = Path(__file__).parent.parent
RAW_DIR  = ROOT / "data" / "raw"
JSON_DIR = ROOT / "data" / "parsed"

sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import parser as trek_parser   # src/parser.py
import loader as trek_loader   # src/loader.py


# ── Phase 1: Fetch ────────────────────────────────────────────────────────────

def run_fetch():
    print("\n══ PHASE 1: FETCH ══════════════════════════════════")
    import fetch_scripts
    downloaded, skipped, failed = fetch_scripts.fetch_all()
    return downloaded, skipped, failed


# ── Phase 2: Parse ────────────────────────────────────────────────────────────

def run_parse():
    print("\n══ PHASE 2: PARSE ══════════════════════════════════")
    JSON_DIR.mkdir(parents=True, exist_ok=True)
    raw_files = sorted(RAW_DIR.glob("*.txt"))
    ok, thin, err = 0, 0, 0

    for raw in raw_files:
        out = JSON_DIR / f"{raw.stem}.json"
        try:
            text = raw.read_text(encoding="utf-8")
            ps   = trek_parser.parse_script(raw.stem, text)
            data = trek_parser.to_dict(ps)
            out.write_text(json.dumps(data, indent=2, ensure_ascii=False))

            n_lines  = len(data.get("lines", []))
            n_chars  = len(data.get("characters", []))
            n_scenes = len(data.get("scenes", []))
            flag = "⚠" if n_lines < 50 else "✓"
            if n_lines < 50:
                thin += 1
            else:
                ok += 1
            title = data.get("title") or "?"
            print(f"  {flag} {raw.stem}  scenes={n_scenes:3d}  lines={n_lines:4d}"
                  f"  chars={n_chars:3d}  → {title[:45]}")
        except Exception as e:
            err += 1
            print(f"  ✗ {raw.stem}  ERROR: {e}")

    print(f"\nParse: ok={ok}  thin(<50 lines)={thin}  errors={err}")
    return ok, thin, err


# ── Phase 3: Load ─────────────────────────────────────────────────────────────

def run_load():
    print("\n══ PHASE 3: LOAD → NEO4J ═══════════════════════════")
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver("bolt://localhost:7688",
                                  auth=("neo4j", "trekgraph"))
    with driver.session() as s:
        s.execute_write(trek_loader.setup_schema)

    json_files = sorted(JSON_DIR.glob("*.json"))
    loaded, errors = 0, 0
    t0 = time.time()

    for jf in json_files:
        try:
            data = json.loads(jf.read_text())
            with driver.session() as session:
                session.execute_write(trek_loader.load_one, data)
            loaded += 1
            title = data.get("title") or "?"
            print(f"  ✓ {jf.stem}  → {title[:50]}")
        except Exception as e:
            errors += 1
            print(f"  ✗ {jf.stem}  ERROR: {e}")

    driver.close()
    print(f"\nLoad: loaded={loaded}  errors={errors}  time={time.time()-t0:.1f}s")
    return loaded, errors


# ── Summary ───────────────────────────────────────────────────────────────────

def print_summary():
    print("\n══ GRAPH SUMMARY ════════════════════════════════════")
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver("bolt://localhost:7688",
                                  auth=("neo4j", "trekgraph"))
    with driver.session() as s:
        for label in ["Episode", "Character", "Scene", "Line", "Location", "Ship"]:
            n = s.run(f"MATCH (n:{label}) RETURN count(n) AS c").single()["c"]  # type: ignore
            print(f"  {label:<12} {n:>8,}")
        print()
        for rel in ["APPEARS_IN", "SPOKEN_BY", "IN_SCENE", "IN_EPISODE", "SET_AT", "FEATURES_SHIP"]:
            n = s.run(f"MATCH ()-[r:{rel}]->() RETURN count(r) AS c").single()["c"]  # type: ignore
            print(f"  {rel:<18} {n:>8,}")
        print()
        top = s.run("""
            MATCH (l:Line)-[:SPOKEN_BY]->(c:Character)
            RETURN c.canonical_name AS name, count(l) AS lines
            ORDER BY lines DESC LIMIT 15
        """).data()
        print("  Top 15 characters by line count:")
        for r in top:
            print(f"    {r['name']:<22} {r['lines']:>6,}")
    driver.close()


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Full TNG ingest pipeline")
    ap.add_argument("--parse-only", action="store_true", help="Skip fetch")
    ap.add_argument("--load-only",  action="store_true", help="Skip fetch + parse")
    args = ap.parse_args()

    t_start = time.time()

    if not args.parse_only and not args.load_only:
        run_fetch()

    if not args.load_only:
        run_parse()

    run_load()
    print_summary()
    print(f"\nTotal wall time: {time.time()-t_start:.1f}s")
