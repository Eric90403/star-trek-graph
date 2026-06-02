#!/usr/bin/env python3
"""
Full TOS ingest: fetch all 79 TOS transcripts from chakoteya.net,
parse them, load into Neo4j (series="TOS").  Idempotent: safe to re-run.

Usage:
    python scripts/ingest_tos.py              # full run
    python scripts/ingest_tos.py --parse-only # skip fetch
    python scripts/ingest_tos.py --load-only  # skip fetch + parse
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
JSON_DIR = ROOT / "data" / "parsed"

sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import config                       # noqa: E402
import tos_parser                   # noqa: E402 — src/tos_parser.py
import loader as trek_loader        # noqa: E402 — src/loader.py


# ── Phase 1: Fetch ────────────────────────────────────────────────────────────

def run_fetch():
    print("\n══ PHASE 1: FETCH ══════════════════════════════════")
    import fetch_tos
    return fetch_tos.fetch_all()


# ── Phase 2: Parse ────────────────────────────────────────────────────────────

def run_parse():
    print("\n══ PHASE 2: PARSE ══════════════════════════════════")
    JSON_DIR.mkdir(parents=True, exist_ok=True)
    raw_files = sorted(RAW_DIR.glob("tos_*.htm*"),
                       key=lambda p: _sort_key(p.stem))
    ok, thin, err = 0, 0, 0
    failures: list[tuple[str, str]] = []

    for raw in raw_files:
        try:
            ps = tos_parser.parse_file(raw)
            data = tos_parser.to_dict(ps)
            out = JSON_DIR / f"{ps.id.replace(':', '_')}.json"
            out.write_text(json.dumps(data, indent=2, ensure_ascii=False))

            n_lines = len(data["lines"])
            n_scenes = len(data["scenes"])
            n_chars = len(data["characters"])
            flag = "⚠" if n_lines < 100 else "✓"
            if n_lines < 100:
                thin += 1
            else:
                ok += 1
            title = data.get("title") or "?"
            print(f"  {flag} {ps.id}  scenes={n_scenes:3d}  lines={n_lines:4d}"
                  f"  chars={n_chars:3d}  → {title[:45]}")
        except Exception as e:
            err += 1
            failures.append((raw.stem, str(e)))
            print(f"  ✗ {raw.stem}  ERROR: {e}")

    print(f"\nParse: ok={ok}  thin(<100 lines)={thin}  errors={err}")
    return ok, thin, err, failures


def _sort_key(stem: str) -> tuple[int, str]:
    # tos_16b → (16, 'b'); tos_42 → (42, '')
    n = stem.replace("tos_", "")
    digits = "".join(c for c in n if c.isdigit())
    suffix = "".join(c for c in n if not c.isdigit())
    return (int(digits) if digits else 0, suffix)


# ── Phase 3: Load ─────────────────────────────────────────────────────────────

def run_load():
    print("\n══ PHASE 3: LOAD → NEO4J ═══════════════════════════")
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(
        config.NEO4J_URI,
        auth=(config.NEO4J_USER, config.NEO4J_PASSWORD),
    )
    with driver.session() as s:
        s.execute_write(trek_loader.setup_schema)

    json_files = sorted(JSON_DIR.glob("tos_*.json"),
                        key=lambda p: _sort_key(p.stem))
    loaded, errors = 0, 0
    t0 = time.time()
    for jf in json_files:
        try:
            data = json.loads(jf.read_text())
            with driver.session() as session:
                session.execute_write(trek_loader.load_one, data)
            loaded += 1
            title = data.get("title") or "?"
            print(f"  ✓ {data['id']}  → {title[:50]}")
        except Exception as e:
            errors += 1
            print(f"  ✗ {jf.stem}  ERROR: {e}")
    driver.close()
    print(f"\nLoad: loaded={loaded}  errors={errors}  time={time.time()-t0:.1f}s")
    return loaded, errors


# ── Summary ───────────────────────────────────────────────────────────────────

def print_summary():
    print("\n══ TOS CORPUS SUMMARY ══════════════════════════════")
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver(
        config.NEO4J_URI,
        auth=(config.NEO4J_USER, config.NEO4J_PASSWORD),
    )
    with driver.session() as s:
        ep_tos = s.run(
            "MATCH (e:Episode {series:'TOS'}) RETURN count(e) AS c"
        ).single()["c"]
        ep_tng = s.run(
            "MATCH (e:Episode {series:'TNG'}) RETURN count(e) AS c"
        ).single()["c"]
        lines_tos = s.run(
            "MATCH (l:Line)-[:SPOKEN_BY]->(:Character) "
            "WHERE l.episode_id STARTS WITH 'tos:' "
            "RETURN count(l) AS c"
        ).single()["c"]
        print(f"  Episodes (TOS):   {ep_tos}")
        print(f"  Episodes (TNG):   {ep_tng}  ← must remain 176")
        print(f"  Lines    (TOS):   {lines_tos}")
        top = s.run("""
            MATCH (l:Line)-[:SPOKEN_BY]->(c:Character)
            WHERE l.episode_id STARTS WITH 'tos:'
            RETURN c.canonical_name AS name, count(l) AS lines
            ORDER BY lines DESC LIMIT 10
        """).data()
        print("\n  Top 10 TOS characters by line count:")
        for r in top:
            print(f"    {r['name']:<22} {r['lines']:>6,}")
    driver.close()


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Full TOS ingest pipeline")
    ap.add_argument("--parse-only", action="store_true", help="Skip fetch")
    ap.add_argument("--load-only", action="store_true", help="Skip fetch + parse")
    args = ap.parse_args()

    t_start = time.time()
    if not args.parse_only and not args.load_only:
        run_fetch()
    if not args.load_only:
        run_parse()
    run_load()
    print_summary()
    print(f"\nTotal wall time: {time.time()-t_start:.1f}s")
