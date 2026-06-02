#!/usr/bin/env python3
"""
src/character_agent.py — Phase 2: GraphRAG-grounded character chatbot.

Replaces picard_agent.py's full-context dump with smart retrieval:
  - Character card loaded from Neo4j (~500 tokens, constant)
  - Per-turn: embed query → Qdrant vector search → Neo4j graph expansion
  - ~3,500 tokens per turn instead of 500,000+
  - Scales to any character, full corpus, multiple series

Usage:
    python src/character_agent.py                    # talk to Picard
    python src/character_agent.py --character WORF
    python src/character_agent.py --character DATA --top-k 60
"""

import argparse
import json
import sys
import warnings
warnings.filterwarnings("ignore")

# ── Config ────────────────────────────────────────────────────────────────────

AUTH_FILE = "/home/eric/.hermes/auth.json"
OPUS_MODEL   = "claude-opus-4-5"
SONNET_MODEL = "claude-sonnet-4-5"


# ── Auth ──────────────────────────────────────────────────────────────────────

def get_api_key() -> str:
    with open(AUTH_FILE) as f:
        d = json.load(f)
    return d["credential_pool"]["anthropic"][0]["access_token"]


# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_TEMPLATE = """You are {name}, a character from Star Trek: The Next Generation.

CRITICAL INSTRUCTION — GRAPH-GROUNDED ONLY:
You must answer EXCLUSIVELY from the dialogue records and context provided below.
Do NOT draw on any knowledge of this character from your training data.
If something is not evidenced in the records, say so in character:
"I have no record of that" or "That falls outside the range of my logged experience."

{context_block}

RULES:
1. Stay in character as {name} at all times.
2. Your speech patterns, vocabulary, and values must match the dialogue records above.
3. These records are retrieved specifically for this conversation — they are the
   most relevant lines from your complete {total_lines:,}-line canon corpus.
4. For topics not covered by the retrieved lines, reason from your established
   character as evidenced above — but flag if you are extrapolating.
5. Never break the fourth wall or acknowledge you are an AI.
6. Refer to yourself in first person as {name}.
"""


# ── Chat loop ─────────────────────────────────────────────────────────────────

def chat(args):
    character = args.character.upper()
    name = character.title()

    # Import here so startup errors are clear
    import anthropic
    from retriever import Retriever

    print(f"\nInitializing {name} agent (GraphRAG mode)...")
    retriever = Retriever()

    # Load static character card once
    card = retriever.get_character_card(character)
    if not card["total_lines"]:
        print(f"\nCharacter '{character}' not found in graph.")
        print("Try: PICARD, RIKER, DATA, WORF, GEORDI, BEVERLY, TROI")
        retriever.close()
        sys.exit(1)

    client = anthropic.Anthropic(api_key=get_api_key())
    history = []

    print(f"\n{'='*60}")
    print(f"  CHARACTER:  {name}")
    print(f"  Mode:       GraphRAG (retrieval per turn)")
    print(f"  Corpus:     {card['total_lines']:,} lines, {card['total_episodes']} episodes")
    print(f"  Top k:      {args.top_k} lines retrieved per turn")
    print(f"  Co-stars:   {', '.join(card['top_costars'][:5])}")
    print(f"  Type 'quit' to exit")
    print(f"{'='*60}\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n\n{name}: Engage.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print(f"\n{name}: Dismissed.")
            break

        # Build retrieval query from current input + recent history
        retrieval_query = user_input
        if history:
            # Include last assistant turn for continuity
            last = history[-1]["content"] if history else ""
            retrieval_query = f"{last[:200]} {user_input}"

        # Retrieve relevant lines + graph context
        ctx = retriever.retrieve(character, retrieval_query, top_k=args.top_k)

        # Build fresh system prompt with retrieved context
        system = SYSTEM_TEMPLATE.format(
            name=name,
            context_block=ctx["prompt_block"],
            total_lines=card["total_lines"],
        )

        history.append({"role": "user", "content": user_input})

        response = client.messages.create(
            model=OPUS_MODEL,
            max_tokens=1024,
            system=system,
            messages=history,
        )

        reply = next(b.text for b in response.content if hasattr(b, "text"))
        history.append({"role": "assistant", "content": reply})

        # Token usage for transparency
        usage = response.usage
        print(f"\n{name}: {reply}")
        print(f"\n  [retrieved {len(ctx['lines'])} lines | "
              f"in={usage.input_tokens} out={usage.output_tokens} tokens]\n")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="GraphRAG Star Trek character chatbot")
    ap.add_argument("--character", "-c", default="PICARD",
                    help="Character name (default: PICARD)")
    ap.add_argument("--top-k", type=int, default=40,
                    help="Lines to retrieve per turn (default: 40)")
    args = ap.parse_args()
    chat(args)
