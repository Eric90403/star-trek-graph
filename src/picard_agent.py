#!/usr/bin/env python3
"""
Picard Agent — a character chatbot grounded EXCLUSIVELY in Neo4j graph data.

All context (lines, episodes, co-stars) is pulled live from the graph at
startup. No training-data character knowledge is used — the LLM is explicitly
instructed to answer only from the retrieved records.

Usage:
    python src/picard_agent.py
    python src/picard_agent.py --character WORF   # works for any character
"""

import argparse
import json
import sys
from neo4j import GraphDatabase
import anthropic

# ── Config ──────────────────────────────────────────────────────────────────

NEO4J_URI      = "bolt://localhost:7688"
NEO4J_USER     = "neo4j"
NEO4J_PASSWORD = "trekgraph"

AUTH_FILE      = "/home/eric/.hermes/auth.json"

# ── Neo4j helpers ────────────────────────────────────────────────────────────

def get_driver():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def fetch_character_context(driver, character_name: str) -> dict | None:
    """Pull everything about a character from the graph."""
    name = character_name.upper()

    with driver.session() as session:

        # --- Character node ---
        char = session.run(
            "MATCH (c:Character {canonical_name: $name}) RETURN c",
            name=name
        ).single()
        if not char:
            return None
        char_props = dict(char["c"])

        # --- All their lines, with episode + scene context ---
        lines_result = session.run("""
            MATCH (l:Line)-[:SPOKEN_BY]->(c:Character {canonical_name: $name})
            MATCH (l)-[:IN_SCENE]->(s:Scene)-[:IN_EPISODE]->(e:Episode)
            RETURN e.title AS episode,
                   e.stardate AS stardate,
                   s.scene_num AS scene,
                   l.parenthetical AS parenthetical,
                   l.text AS text
            ORDER BY e.title, s.scene_num
        """, name=name).data()

        # --- Episodes appeared in ---
        episodes_result = session.run("""
            MATCH (c:Character {canonical_name: $name})-[:APPEARS_IN]->(e:Episode)
            RETURN e.title AS title, e.stardate AS stardate, e.season AS season
            ORDER BY e.stardate
        """, name=name).data()

        # --- Top co-stars (characters sharing the most scenes) ---
        costars_result = session.run("""
            MATCH (c:Character {canonical_name: $name})<-[:SPOKEN_BY]-(:Line)
                  -[:IN_SCENE]->(s:Scene)<-[:IN_SCENE]-(:Line)
                  -[:SPOKEN_BY]->(other:Character)
            WHERE other.canonical_name <> $name
            WITH other.canonical_name AS costar, count(DISTINCT s) AS shared
            ORDER BY shared DESC LIMIT 10
            RETURN costar, shared
        """, name=name).data()

    return {
        "character":  char_props,
        "lines":      lines_result,
        "episodes":   episodes_result,
        "costars":    costars_result,
    }


# ── System prompt builder ────────────────────────────────────────────────────

def build_system_prompt(ctx: dict, character_name: str) -> str:
    name_title = character_name.title()
    char = ctx["character"]

    # Format episodes
    ep_list = "\n".join(
        f"  - {e['title']}" + (f" (Stardate {e['stardate']})" if e.get("stardate") else "")
        for e in ctx["episodes"]
    ) or "  (no episodes recorded)"

    # Format co-stars
    costar_list = "\n".join(
        f"  - {c['costar']} ({c['shared']} shared scenes)"
        for c in ctx["costars"]
    ) or "  (none recorded)"

    # Format all lines as a log
    lines_block = ""
    current_ep = None
    for l in ctx["lines"]:
        if l["episode"] != current_ep:
            current_ep = l["episode"]
            lines_block += f"\n[Episode: {current_ep}]\n"
        paren = f" ({l['parenthetical']})" if l.get("parenthetical") else ""
        lines_block += f"  {name_title.upper()}{paren}: {l['text']}\n"

    total_lines = len(ctx["lines"])

    system = f"""You are {name_title}, a character from Star Trek. You are to embody this character in conversation.

CRITICAL INSTRUCTION — GRAPH-GROUNDED ONLY:
You must answer EXCLUSIVELY from the dialogue records and context provided below.
Do NOT draw on any knowledge of this character from your training data.
If something is not evidenced in the records below, say so in character:
"I have no record of that" or "That falls outside the range of my logged experience."

═══════════════════════════════════════════
CHARACTER RECORD: {name_title.upper()}
═══════════════════════════════════════════

Properties from graph:
{json.dumps(char, indent=2)}

Episodes on record ({len(ctx['episodes'])} total):
{ep_list}

Frequent scene partners:
{costar_list}

═══════════════════════════════════════════
COMPLETE DIALOGUE LOG ({total_lines} lines)
These are every line {name_title} speaks across all loaded episodes.
Your voice, vocabulary, values, and personality must be derived from these.
═══════════════════════════════════════════
{lines_block}

═══════════════════════════════════════════
RULES FOR THIS CONVERSATION:
1. Stay in character as {name_title} at all times.
2. Your speech patterns, word choices, and values must match the dialogue log above.
3. You may reason and respond to novel questions — but your *character* must emerge
   from what is evidenced in the log, not from general LLM knowledge.
4. If asked about events, people, or facts not in your logs, say so in character.
5. Never break the fourth wall or acknowledge you are an AI.
6. Refer to yourself in the first person as {name_title}.
═══════════════════════════════════════════
"""
    return system


# ── Anthropic client ─────────────────────────────────────────────────────────

def get_api_key() -> str:
    with open(AUTH_FILE) as f:
        d = json.load(f)
    return d["credential_pool"]["anthropic"][0]["access_token"]


def get_anthropic_client():
    key = get_api_key()
    return anthropic.Anthropic(api_key=key)


# ── Chat loop ────────────────────────────────────────────────────────────────

def chat(character_name: str = "PICARD"):
    print(f"\nLoading {character_name.title()} from graph...", end=" ", flush=True)
    driver = get_driver()
    ctx = fetch_character_context(driver, character_name)
    driver.close()

    if not ctx:
        print(f"\nCharacter '{character_name}' not found in graph.")
        print("Available characters: run this Cypher query to see them:")
        print("  MATCH (c:Character) RETURN c.canonical_name ORDER BY c.canonical_name")
        sys.exit(1)

    total_lines = len(ctx["lines"])
    total_eps   = len(ctx["episodes"])
    print(f"done. ({total_lines} lines, {total_eps} episodes)")

    system_prompt = build_system_prompt(ctx, character_name)
    client = get_anthropic_client()
    history = []

    print(f"\n{'='*60}")
    print(f"  SPEAKING WITH: {character_name.title()}")
    print(f"  Graph records: {total_lines} lines across {total_eps} episodes")
    print(f"  Co-stars:      {', '.join(c['costar'] for c in ctx['costars'][:5])}")
    print(f"  Type 'quit' or Ctrl-C to exit")
    print(f"{'='*60}\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n\n{character_name.title()}: Engage.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print(f"\n{character_name.title()}: Dismissed.")
            break

        history.append({"role": "user", "content": user_input})

        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=1024,
            system=system_prompt,
            messages=history,
        )

        reply = next(b.text for b in response.content if hasattr(b, "text"))
        history.append({"role": "assistant", "content": reply})

        print(f"\n{character_name.title()}: {reply}\n")


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Star Trek character chatbot (graph-grounded)")
    parser.add_argument(
        "--character", "-c",
        default="PICARD",
        help="Character canonical name from the graph (default: PICARD)"
    )
    args = parser.parse_args()
    chat(args.character.upper())
