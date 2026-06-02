#!/usr/bin/env python3
"""
src/character_agent.py — GraphRAG-grounded character chatbot.

Per turn:
  1. Embed the user message
  2. Retrieve top-k canon lines from Qdrant (filtered by speaker)
  3. Expand context via Neo4j graph hops
  4. Assemble a ~3-4k token system prompt
  5. Generate a reply with Claude

Usage:
    ./trek                                  # talk to Picard
    ./trek --character WORF
    ./trek --character DATA --top-k 60
    ./trek --model claude-sonnet-4-5        # cheaper, faster
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import warnings

warnings.filterwarnings("ignore")

# Local imports
sys.path.insert(0, os.path.dirname(__file__))
from auth import get_api_key                                          # noqa: E402
from config import (                                                  # noqa: E402
    DEFAULT_LLM_MODEL, DEFAULT_TOP_K,
    HISTORY_TURNS_KEPT, MAX_OUTPUT_TOKENS,
    __version__,
)


# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_TEMPLATE = """You are {name}, a character from Star Trek ({series}).

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


# ── LLM call with retry ───────────────────────────────────────────────────────

def call_llm_with_retry(client, *, model, system, messages,
                        max_tokens, max_retries=3):
    """One call to the Anthropic API with exponential backoff on transient
    errors. Returns (reply_text, usage) or raises after exhausting retries."""
    import anthropic

    for attempt in range(max_retries):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
            )
            text = next(b.text for b in response.content if hasattr(b, "text"))
            return text, response.usage
        except (anthropic.APIConnectionError, anthropic.APIStatusError,
                anthropic.RateLimitError) as exc:
            if attempt == max_retries - 1:
                raise
            delay = 2 ** attempt
            print(f"\n  [API hiccup: {type(exc).__name__} — retrying in {delay}s]",
                  flush=True)
            time.sleep(delay)
    raise RuntimeError("unreachable")  # keep type checker happy


# ── Chat loop ─────────────────────────────────────────────────────────────────

def chat(args: argparse.Namespace) -> int:
    # Import heavy stuff only after argparse so --help is fast
    import anthropic
    from retriever import Retriever, EmptyCollectionError

    character = args.character.upper()
    name = character.title()

    print(f"\nInitializing {name} agent (GraphRAG, trek-graph v{__version__})...")
    try:
        retriever = Retriever()
    except EmptyCollectionError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    card = retriever.get_character_card(character)
    if not card["total_lines"]:
        print(f"\nCharacter '{character}' not found in the graph.", file=sys.stderr)
        print("\nTry one of these top-by-lines characters:", file=sys.stderr)
        print("  PICARD, RIKER, DATA, GEORDI, WORF, BEVERLY, TROI, WESLEY",
              file=sys.stderr)
        retriever.close()
        return 1

    try:
        client = anthropic.Anthropic(api_key=get_api_key())
    except RuntimeError as exc:
        # auth.py raises a clear setup-instructions error; surface and exit
        print(str(exc), file=sys.stderr)
        retriever.close()
        return 1

    history: list[dict] = []

    print(f"\n{'='*60}")
    print(f"  CHARACTER:  {name}")
    print(f"  Mode:       GraphRAG (retrieval per turn)")
    print(f"  Corpus:     {card['total_lines']:,} lines, "
          f"{card['total_episodes']} episodes")
    print(f"  Top-k:      {args.top_k} lines retrieved per turn")
    print(f"  Co-stars:   {', '.join(card['top_costars'][:5])}")
    print(f"  Model:      {args.model}")
    print(f"  Type 'quit' to exit, 'reset' to clear conversation history.")
    print(f"{'='*60}\n")

    try:
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
            if user_input.lower() == "reset":
                history = []
                print("(history cleared)\n")
                continue

            # Build the retrieval query: last assistant turn (for continuity)
            # plus the new user message.
            retrieval_query = user_input
            if history:
                last_assistant = history[-1]["content"]
                retrieval_query = f"{last_assistant[:200]} {user_input}"

            ctx = retriever.retrieve(character, retrieval_query,
                                     top_k=args.top_k,
                                     series=args.series)

            system = SYSTEM_TEMPLATE.format(
                name=name,
                series=args.series or "the canon corpus",
                context_block=ctx["prompt_block"],
                total_lines=card["total_lines"],
            )

            history.append({"role": "user", "content": user_input})

            # Keep only the last N turns of history to bound context growth
            trimmed = history[-(HISTORY_TURNS_KEPT * 2):]

            try:
                reply, usage = call_llm_with_retry(
                    client,
                    model=args.model,
                    system=system,
                    messages=trimmed,
                    max_tokens=MAX_OUTPUT_TOKENS,
                )
            except Exception as exc:
                print(f"\n[Anthropic API error after retries: {exc}]")
                print("[Conversation preserved — try again, or 'quit' to exit.]\n")
                history.pop()  # un-record the user turn that failed
                continue

            history.append({"role": "assistant", "content": reply})

            print(f"\n{name}: {reply}")
            print(f"\n  [retrieved {len(ctx['lines'])} lines | "
                  f"in={usage.input_tokens} out={usage.output_tokens} tokens]\n")
    finally:
        retriever.close()

    return 0


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(
        description="GraphRAG Star Trek character chatbot",
    )
    ap.add_argument("--character", "-c", default="PICARD",
                    help="Character canonical name (default: PICARD)")
    ap.add_argument("--top-k", type=int, default=DEFAULT_TOP_K,
                    help=f"Lines retrieved per turn (default: {DEFAULT_TOP_K})")
    ap.add_argument("--series", default=None,
                    help="Restrict retrieval to one series: TNG, TOS, etc. "
                         "Default: any series (useful when characters span shows).")
    ap.add_argument("--model", default=DEFAULT_LLM_MODEL,
                    help=f"Anthropic model id (default: {DEFAULT_LLM_MODEL}). "
                         "Use claude-sonnet-4-5 for faster/cheaper responses.")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return chat(ap.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
