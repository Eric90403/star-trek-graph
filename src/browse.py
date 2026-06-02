#!/usr/bin/env python3
"""
src/browse.py — No-API-key tire-kicker mode.

Browse the graph without an Anthropic key: see a character's stats, their
most distinctive lines, episode appearances, and frequent scene partners.
Useful for exploring the corpus before committing to LLM-backed chat.

Usage:
    ./trek-browse                       # show top characters across all series
    ./trek-browse PICARD                # detailed view of one character
    ./trek-browse KIRK --series TOS
    ./trek-browse SISKO --series DS9 --top-lines 20
    ./trek-browse --episode 175         # episode detail (cast, scenes, top lines)
"""

from __future__ import annotations

import argparse
import os
import sys

# Local imports
sys.path.insert(0, os.path.dirname(__file__))
from config import (                                                  # noqa: E402
    NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, __version__,
)

from neo4j import GraphDatabase                                       # noqa: E402


# ── Helpers ───────────────────────────────────────────────────────────────────

def fmt_num(n: int | float | None) -> str:
    if n is None:
        return "—"
    return f"{n:,}"


def hbar(label: str, value: int, max_value: int, width: int = 30) -> str:
    """Render a horizontal bar for a metric."""
    if max_value <= 0:
        return f"  {label:<22} {value}"
    filled = int(width * value / max_value)
    bar = "█" * filled + "·" * (width - filled)
    return f"  {label:<22} {bar} {value:,}"


# ── Queries ───────────────────────────────────────────────────────────────────

def top_characters(session, series: str | None = None, limit: int = 20) -> list[dict]:
    if series:
        query = """
            MATCH (l:Line)-[:SPOKEN_BY]->(c:Character)
            MATCH (l)-[:IN_SCENE]->(:Scene)-[:IN_EPISODE]->(e:Episode {series: $series})
            WITH c, count(l) AS lines
            ORDER BY lines DESC LIMIT $limit
            RETURN c.canonical_name AS name, lines
        """
        params = {"series": series.upper(), "limit": limit}
    else:
        query = """
            MATCH (l:Line)-[:SPOKEN_BY]->(c:Character)
            WITH c, count(l) AS lines
            ORDER BY lines DESC LIMIT $limit
            RETURN c.canonical_name AS name, lines
        """
        params = {"limit": limit}
    return session.run(query, **params).data()


def series_summary(session) -> list[dict]:
    return session.run("""
        MATCH (e:Episode)
        WITH coalesce(e.series, 'UNKNOWN') AS series, count(e) AS episodes
        MATCH (l:Line)-[:IN_SCENE]->(:Scene)-[:IN_EPISODE]->(e2:Episode)
        WHERE coalesce(e2.series, 'UNKNOWN') = series
        RETURN series, episodes, count(l) AS lines
        ORDER BY series
    """).data()


def character_detail(session, name: str, top_lines: int = 10,
                     series: str | None = None) -> dict:
    name = name.upper()

    char = session.run(
        "MATCH (c:Character {canonical_name: $name}) RETURN c",
        name=name,
    ).single()
    if not char:
        return {}

    stats = session.run("""
        MATCH (c:Character {canonical_name: $name})
        OPTIONAL MATCH (l:Line)-[:SPOKEN_BY]->(c)
        OPTIONAL MATCH (l)-[:IN_SCENE]->(:Scene)-[:IN_EPISODE]->(e:Episode)
        RETURN count(DISTINCT l) AS lines, count(DISTINCT e) AS episodes
    """, name=name).single()

    series_breakdown = session.run("""
        MATCH (l:Line)-[:SPOKEN_BY]->(c:Character {canonical_name: $name})
        MATCH (l)-[:IN_SCENE]->(:Scene)-[:IN_EPISODE]->(e:Episode)
        WITH coalesce(e.series, 'UNKNOWN') AS series, count(l) AS lines
        RETURN series, lines ORDER BY lines DESC
    """, name=name).data()

    series_filter = "AND e.series = $series" if series else ""
    longest_lines = session.run(f"""
        MATCH (l:Line)-[:SPOKEN_BY]->(c:Character {{canonical_name: $name}})
        MATCH (l)-[:IN_SCENE]->(s:Scene)-[:IN_EPISODE]->(e:Episode)
        WHERE size(l.text) > 80 {series_filter}
        WITH e, l, size(l.text) AS sz
        ORDER BY sz DESC LIMIT $limit
        RETURN e.title AS episode, e.series AS series,
               substring(l.text, 0, 200) AS line, sz AS length
    """, name=name, series=(series.upper() if series else None),
        limit=top_lines).data()

    top_costars = session.run("""
        MATCH (c:Character {canonical_name: $name})<-[:SPOKEN_BY]-(:Line)
              -[:IN_SCENE]->(s:Scene)<-[:IN_SCENE]-(:Line)
              -[:SPOKEN_BY]->(other:Character)
        WHERE other.canonical_name <> $name
        WITH other.canonical_name AS costar, count(DISTINCT s) AS shared
        ORDER BY shared DESC LIMIT 10
        RETURN costar, shared
    """, name=name).data()

    episode_breakdown = session.run("""
        MATCH (c:Character {canonical_name: $name})<-[:SPOKEN_BY]-(:Line)
              -[:IN_SCENE]->(:Scene)-[:IN_EPISODE]->(e:Episode)
        WITH e, count(DISTINCT _) AS dummy, count(*) AS line_count
        WHERE 1=1
        RETURN e.title AS title, e.series AS series, line_count
        ORDER BY line_count DESC LIMIT 8
    """, name=name).data() if False else []
    # NB: easier rewrite of that
    episode_breakdown = session.run("""
        MATCH (l:Line)-[:SPOKEN_BY]->(c:Character {canonical_name: $name})
        MATCH (l)-[:IN_SCENE]->(:Scene)-[:IN_EPISODE]->(e:Episode)
        WITH e, count(l) AS lines
        ORDER BY lines DESC LIMIT 8
        RETURN e.title AS title, e.series AS series, lines
    """, name=name).data()

    return {
        "props":            dict(char["c"]),
        "lines":            stats["lines"] or 0,
        "episodes":         stats["episodes"] or 0,
        "series_breakdown": series_breakdown,
        "longest_lines":    longest_lines,
        "top_costars":      top_costars,
        "episode_breakdown": episode_breakdown,
    }


def episode_detail(session, episode_id: str) -> dict:
    ep = session.run(
        "MATCH (e:Episode {id: $id}) RETURN e",
        id=episode_id,
    ).single()
    if not ep:
        return {}

    cast = session.run("""
        MATCH (l:Line)-[:SPOKEN_BY]->(c:Character)
        MATCH (l)-[:IN_SCENE]->(:Scene)-[:IN_EPISODE]->(e:Episode {id: $id})
        WITH c, count(l) AS lines
        ORDER BY lines DESC
        RETURN c.canonical_name AS name, lines
    """, id=episode_id).data()

    top_lines_q = session.run("""
        MATCH (l:Line)-[:SPOKEN_BY]->(c:Character)
        MATCH (l)-[:IN_SCENE]->(:Scene)-[:IN_EPISODE]->(e:Episode {id: $id})
        WHERE size(l.text) > 80
        WITH c, l, size(l.text) AS sz
        ORDER BY sz DESC LIMIT 8
        RETURN c.canonical_name AS speaker,
               substring(l.text, 0, 200) AS line, sz AS length
    """, id=episode_id).data()

    return {
        "props": dict(ep["e"]),
        "cast": cast,
        "top_lines": top_lines_q,
    }


# ── Renderers ─────────────────────────────────────────────────────────────────

def banner(title: str, char: str = "═") -> None:
    print()
    print(char * 60)
    print(f"  {title}")
    print(char * 60)


def render_overview(driver) -> None:
    with driver.session() as s:
        summary = series_summary(s)
        top = top_characters(s, limit=15)

    banner(f"Star Trek Graph — v{__version__} corpus overview")
    print()
    print(f"  {'Series':<8} {'Episodes':>10} {'Lines':>12}")
    print(f"  {'-'*8} {'-'*10} {'-'*12}")
    total_eps, total_lines = 0, 0
    for row in summary:
        print(f"  {row['series']:<8} {fmt_num(row['episodes']):>10} {fmt_num(row['lines']):>12}")
        total_eps += row["episodes"]
        total_lines += row["lines"]
    print(f"  {'-'*8} {'-'*10} {'-'*12}")
    print(f"  {'TOTAL':<8} {fmt_num(total_eps):>10} {fmt_num(total_lines):>12}")

    banner("Top 15 characters by total line count")
    print()
    max_lines = max((r["lines"] for r in top), default=1)
    for r in top:
        print(hbar(r["name"], r["lines"], max_lines))
    print()
    print("Try:")
    print("  ./trek-browse PICARD                 (detailed character view)")
    print("  ./trek-browse KIRK --series TOS")
    print("  ./trek-browse SISKO --series DS9")
    print("  ./trek-browse --episode 175          (episode detail)")
    print()


def render_character(driver, name: str, top_lines: int = 10,
                     series: str | None = None) -> int:
    with driver.session() as s:
        d = character_detail(s, name, top_lines=top_lines, series=series)

    if not d:
        print(f"\nCharacter '{name}' not found.")
        print("\nTip: names are stored upper-case. Try PICARD, KIRK, SISKO, etc.")
        print("Run `./trek-browse` (no args) to see top characters.")
        return 1

    banner(f"  {name.upper()}  ·  {fmt_num(d['lines'])} lines  ·  {fmt_num(d['episodes'])} episodes")

    if d["props"]:
        print()
        for k, v in d["props"].items():
            if v and k != "canonical_name":
                print(f"  {k}: {v}")

    if d["series_breakdown"]:
        print()
        print("  Lines by series:")
        for row in d["series_breakdown"]:
            print(f"    {row['series']:<6} {fmt_num(row['lines']):>8}")

    if d["top_costars"]:
        banner("Top 10 scene partners (by shared scenes)", "─")
        print()
        max_v = max(c["shared"] for c in d["top_costars"])
        for c in d["top_costars"]:
            print(hbar(c["costar"], c["shared"], max_v))

    if d["episode_breakdown"]:
        banner("Top 8 episodes by lines spoken", "─")
        print()
        max_v = max(e["lines"] for e in d["episode_breakdown"])
        for e in d["episode_breakdown"]:
            label = f"[{e['series']}] {e['title'][:35]}"
            print(hbar(label, e["lines"], max_v))

    if d["longest_lines"]:
        banner(f"Top {top_lines} longest speeches", "─")
        for ln in d["longest_lines"]:
            print()
            print(f"  [{ln['series']}] {ln['episode']} ({ln['length']} chars)")
            # Word-wrap the line at 70 chars for terminal readability
            words = ln["line"].split()
            line, cur = [], 0
            for w in words:
                if cur + len(w) + 1 > 70:
                    print(f"    {' '.join(line)}")
                    line, cur = [w], len(w)
                else:
                    line.append(w)
                    cur += len(w) + 1
            if line:
                print(f"    {' '.join(line)}")
    print()
    return 0


def render_episode(driver, episode_id: str) -> int:
    with driver.session() as s:
        d = episode_detail(s, episode_id)

    if not d:
        print(f"\nEpisode '{episode_id}' not found in graph.")
        print("\nTip: episode IDs are bare numbers, e.g. 175 (Best of Both Worlds Pt II)")
        print("or 'tos:42' (Trouble With Tribbles) or '402' (Emissary, DS9).")
        return 1

    p = d["props"]
    banner(f"  {p.get('title') or 'Untitled'}  ·  id={p.get('id')}  ·  series={p.get('series', 'UNKNOWN')}")
    print()
    for k in ("stardate", "writer", "director", "production_code", "canon_tier"):
        if p.get(k):
            print(f"  {k}: {p[k]}")

    if d["cast"]:
        banner("Cast (lines spoken)", "─")
        print()
        max_v = max(c["lines"] for c in d["cast"])
        for c in d["cast"][:15]:
            print(hbar(c["name"], c["lines"], max_v))

    if d["top_lines"]:
        banner("Notable lines", "─")
        for ln in d["top_lines"]:
            print()
            print(f"  {ln['speaker']} ({ln['length']} chars):")
            words = ln["line"].split()
            line, cur = [], 0
            for w in words:
                if cur + len(w) + 1 > 70:
                    print(f"    {' '.join(line)}")
                    line, cur = [w], len(w)
                else:
                    line.append(w); cur += len(w) + 1
            if line:
                print(f"    {' '.join(line)}")
    print()
    return 0


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Browse the Star Trek Graph corpus (no API key required).",
    )
    ap.add_argument("character", nargs="?", default=None,
                    help="Character name (e.g. PICARD). Omit to see overview.")
    ap.add_argument("--series", default=None,
                    help="Scope to one series: TNG, TOS, DS9.")
    ap.add_argument("--top-lines", type=int, default=5,
                    help="Number of longest speeches to show (default 5).")
    ap.add_argument("--episode", default=None,
                    help="Episode ID to show detail for (e.g. 175 or 402 or tos:42).")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = ap.parse_args()

    try:
        driver = GraphDatabase.driver(NEO4J_URI,
                                      auth=(NEO4J_USER, NEO4J_PASSWORD))
    except Exception as exc:
        print(f"\nCould not connect to Neo4j at {NEO4J_URI}.")
        print(f"  Is the trek-neo4j container running? (docker compose up -d)")
        print(f"  Original error: {exc}\n")
        return 1

    try:
        if args.episode:
            return render_episode(driver, args.episode)
        if args.character:
            return render_character(driver, args.character,
                                    top_lines=args.top_lines,
                                    series=args.series)
        render_overview(driver)
        return 0
    finally:
        driver.close()


if __name__ == "__main__":
    raise SystemExit(main())
