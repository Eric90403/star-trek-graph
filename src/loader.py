#!/usr/bin/env python3
"""Load parsed scripts JSON into Neo4j (Layer 1)."""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from neo4j import GraphDatabase

log = logging.getLogger("trek.loader")

URI = os.environ.get("NEO4J_URI", "bolt://localhost:7688")
USER = os.environ.get("NEO4J_USER", "neo4j")
PW = os.environ.get("NEO4J_PASSWORD", "trekgraph")

CONSTRAINTS = [
    "CREATE CONSTRAINT episode_id IF NOT EXISTS FOR (e:Episode) REQUIRE e.id IS UNIQUE",
    "CREATE CONSTRAINT character_name IF NOT EXISTS FOR (c:Character) REQUIRE c.canonical_name IS UNIQUE",
    "CREATE CONSTRAINT ship_name IF NOT EXISTS FOR (s:Ship) REQUIRE s.name IS UNIQUE",
    "CREATE CONSTRAINT location_name IF NOT EXISTS FOR (l:Location) REQUIRE l.name IS UNIQUE",
    "CREATE CONSTRAINT scene_id IF NOT EXISTS FOR (s:Scene) REQUIRE s.id IS UNIQUE",
    "CREATE CONSTRAINT line_id IF NOT EXISTS FOR (l:Line) REQUIRE l.id IS UNIQUE",
]


def setup_schema(tx):
    for q in CONSTRAINTS:
        tx.run(q)


def load_one(tx, ep: dict) -> None:
    eid = ep["id"]
    tx.run(
        """
        MERGE (e:Episode {id: $id})
        SET e.title = $title, e.series = $series, e.writer = $writer,
            e.director = $director, e.stardate = $stardate,
            e.production_code = $production_code, e.canon_tier = 1
        """,
        id=eid,
        title=ep.get("title"),
        series=ep.get("series"),
        writer=ep.get("writer"),
        director=ep.get("director"),
        stardate=ep.get("stardate"),
        production_code=ep.get("production_code"),
    )

    # Locations
    for loc in ep.get("locations", []):
        tx.run("MERGE (:Location {name: $name})", name=loc)

    # Ships + FEATURES_SHIP
    for s in ep.get("ships", []):
        tx.run(
            """
            MERGE (sh:Ship {name: $name})
            WITH sh
            MATCH (e:Episode {id: $eid})
            MERGE (e)-[:FEATURES_SHIP]->(sh)
            """,
            name=s, eid=eid,
        )

    # Scenes
    for sc in ep.get("scenes", []):
        sid = f"{eid}:s{sc['scene_idx']}"
        tx.run(
            """
            MERGE (s:Scene {id: $sid})
            SET s.episode_id = $eid, s.scene_num = $num, s.heading = $heading,
                s.int_ext = $int_ext, s.act = $act
            WITH s
            MATCH (e:Episode {id: $eid})
            MERGE (s)-[:IN_EPISODE]->(e)
            """,
            sid=sid, eid=eid,
            num=sc.get("number"), heading=sc.get("heading"),
            int_ext=sc.get("int_ext"), act=sc.get("act"),
        )
        if sc.get("location"):
            tx.run(
                """
                MERGE (l:Location {name: $loc})
                WITH l
                MATCH (s:Scene {id: $sid})
                MERGE (s)-[:SET_AT]->(l)
                """,
                loc=sc["location"], sid=sid,
            )

    # Characters
    for ch in ep.get("characters", []):
        tx.run(
            """
            MERGE (c:Character {canonical_name: $name})
            ON CREATE SET c.aliases = []
            """,
            name=ch["canonical_name"],
        )

    # Lines + SPOKEN_BY + IN_SCENE + accumulate APPEARS_IN counts
    char_line_counts: dict[str, int] = {}
    char_scene_sets: dict[str, set] = {}
    for li in ep.get("lines", []):
        lid = f"{eid}:l{li['line_num']}"
        sid = f"{eid}:s{li['scene_idx']}" if li.get("scene_idx") else None
        tx.run(
            """
            MERGE (l:Line {id: $lid})
            SET l.line_num = $num, l.text = $text, l.parenthetical = $paren,
                l.episode_id = $eid
            WITH l
            MATCH (c:Character {canonical_name: $sp})
            MERGE (l)-[:SPOKEN_BY]->(c)
            """,
            lid=lid, num=li["line_num"], text=li["text"],
            paren=li.get("parenthetical"), eid=eid, sp=li["speaker"],
        )
        if sid:
            tx.run(
                """
                MATCH (l:Line {id: $lid}), (s:Scene {id: $sid})
                MERGE (l)-[:IN_SCENE]->(s)
                """,
                lid=lid, sid=sid,
            )
        char_line_counts[li["speaker"]] = char_line_counts.get(li["speaker"], 0) + 1
        char_scene_sets.setdefault(li["speaker"], set()).add(li.get("scene_idx"))

    for name, lc in char_line_counts.items():
        tx.run(
            """
            MATCH (c:Character {canonical_name: $name}), (e:Episode {id: $eid})
            MERGE (c)-[r:APPEARS_IN]->(e)
            SET r.line_count = $lc, r.scene_count = $sc
            """,
            name=name, eid=eid, lc=lc, sc=len(char_scene_sets[name]),
        )


def counts(driver) -> dict:
    out = {"nodes": {}, "edges": {}}
    with driver.session() as s:
        labels = ["Episode", "Character", "Scene", "Line", "Ship", "Location"]
        for lbl in labels:
            r = s.run(f"MATCH (n:`{lbl}`) RETURN count(n) AS c").single()
            out["nodes"][lbl] = r["c"] if r else 0
        rels = ["APPEARS_IN", "SPOKEN_BY", "IN_SCENE", "IN_EPISODE", "SET_AT", "FEATURES_SHIP"]
        for rt in rels:
            r = s.run(f"MATCH ()-[r:`{rt}`]->() RETURN count(r) AS c").single()
            out["edges"][rt] = r["c"] if r else 0
    return out


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    logging.getLogger("neo4j.notifications").setLevel(logging.WARNING)
    root = Path(__file__).resolve().parents[1]
    parsed = sorted((root / "data" / "parsed").glob("*.json"))
    if not parsed:
        log.error("No parsed JSON files found")
        return 1

    log.info("Connecting to %s", URI)
    driver = GraphDatabase.driver(URI, auth=(USER, PW))
    try:
        with driver.session() as s:
            s.execute_write(setup_schema)
        for p in parsed:
            ep = json.loads(p.read_text())
            with driver.session() as s:
                s.execute_write(load_one, ep)
            log.info("loaded %s (%d lines, %d scenes)",
                     ep["id"], len(ep.get("lines", [])), len(ep.get("scenes", [])))
        c = counts(driver)
        print("\n=== Graph counts ===")
        print("Nodes:")
        for k, v in c["nodes"].items():
            print(f"  {k:12s} {v}")
        print("Edges:")
        for k, v in c["edges"].items():
            print(f"  {k:14s} {v}")
    finally:
        driver.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
