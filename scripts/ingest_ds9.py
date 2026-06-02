#!/usr/bin/env python3
"""
Full DS9 ingest: fetch all 173 available DS9 scripts, parse with the TNG
screenplay parser (DS9 uses the same st-minutiae format), inject
series="DS9" into the JSON, then load into Neo4j.

Safe to re-run: skips already-fetched files, uses MERGE in Neo4j.

Episode IDs in Neo4j are the bare source numbers (e.g. "402", "575").
TNG occupies 102-277 so there is no collision. The series property
distinguishes them.

Usage:
    python scripts/ingest_ds9.py              # full run
    python scripts/ingest_ds9.py --parse-only # skip fetch
    python scripts/ingest_ds9.py --load-only  # skip fetch + parse
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT     = Path(__file__).resolve().parent.parent
RAW_DIR  = ROOT / "data" / "raw"
JSON_DIR = ROOT / "data" / "parsed"

sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import config                       # noqa: E402 — src/config.py
import parser as trek_parser        # noqa: E402 — src/parser.py
import loader as trek_loader        # noqa: E402 — src/loader.py


# ── Phase 1: Fetch ────────────────────────────────────────────────────────────

def run_fetch():
    print("\n══ PHASE 1: FETCH ══════════════════════════════════")
    import fetch_ds9
    return fetch_ds9.fetch_all()


# ── Phase 2: Parse ────────────────────────────────────────────────────────────

def run_parse():
    print("\n══ PHASE 2: PARSE ══════════════════════════════════")
    JSON_DIR.mkdir(parents=True, exist_ok=True)
    raw_files = sorted(RAW_DIR.glob("ds9_*.txt"),
                       key=lambda p: int(p.stem.split("_")[1]))
    ok, thin, err = 0, 0, 0
    failures: list[tuple[str, str]] = []

    for raw in raw_files:
        script_num = raw.stem.split("_")[1]   # "ds9_402" -> "402"
        out = JSON_DIR / f"ds9_{script_num}.json"
        try:
            text = raw.read_text(encoding="utf-8", errors="replace")
            ps   = trek_parser.parse_script(script_num, text)
            data = trek_parser.to_dict(ps)
            # Inject DS9 series tag (parser default is "TNG")
            data["series"] = "DS9"
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
            print(f"  {flag} ds9_{script_num}  scenes={n_scenes:3d}  lines={n_lines:4d}"
                  f"  chars={n_chars:3d}  → {title[:45]}")
        except Exception as e:
            err += 1
            failures.append((raw.stem, str(e)))
            print(f"  ✗ {raw.stem}  ERROR: {e}")

    print(f"\nParse: ok={ok}  thin(<50 lines)={thin}  errors={err}")
    return ok, thin, err, failures


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

    json_files = sorted(JSON_DIR.glob("ds9_*.json"),
                        key=lambda p: int(p.stem.split("_")[1]))
    loaded, errors = 0, 0
    t0 = time.time()
    for jf in json_files:
        try:
            data = json.loads(jf.read_text())
            # Defensive: make sure series is set even on older JSONs
            if data.get("series") != "DS9":
                data["series"] = "DS9"
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
    print("\n══ DS9 CORPUS SUMMARY ══════════════════════════════")
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver(
        config.NEO4J_URI,
        auth=(config.NEO4J_USER, config.NEO4J_PASSWORD),
    )
    with driver.session() as s:
        ep_ds9 = s.run(
            "MATCH (e:Episode {series:'DS9'}) RETURN count(e) AS c"
        ).single()["c"]
        ep_tng = s.run(
            "MATCH (e:Episode {series:'TNG'}) RETURN count(e) AS c"
        ).single()["c"]
        ep_tos = s.run(
            "MATCH (e:Episode {series:'TOS'}) RETURN count(e) AS c"
        ).single()["c"]
        lines_ds9 = s.run(
            "MATCH (l:Line)-[:SPOKEN_BY]->(:Character) "
            "WHERE l.episode_id IN "
            "  [x IN range(402,575) WHERE x <> 473 | toString(x)] "
            "RETURN count(l) AS c"
        ).single()["c"]
        print(f"  Episodes (DS9):   {ep_ds9}   (target 173)")
        print(f"  Episodes (TNG):   {ep_tng}   (must remain 176)")
        print(f"  Episodes (TOS):   {ep_tos}   (must remain 80)")
        print(f"  Lines    (DS9):   {lines_ds9:,}")
        top = s.run("""
            MATCH (l:Line)-[:SPOKEN_BY]->(c:Character)
            WHERE l.episode_id IN
              [x IN range(402,575) WHERE x <> 473 | toString(x)]
            RETURN c.canonical_name AS name, count(l) AS lines
            ORDER BY lines DESC LIMIT 10
        """).data()
        print("\n  Top 10 DS9 characters by line count:")
        for r in top:
            print(f"    {r['name']:<22} {r['lines']:>6,}")
    driver.close()


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Full DS9 ingest pipeline")
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
