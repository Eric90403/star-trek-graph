"""
src/behavioral_extractor.py — Layer 2 (BehavioralCard) extraction.

Extracts character "bibles" derived strictly from canon dialogue stored
in the Neo4j graph. Each card is stored as a BehavioralCard node attached
to its Character via HAS_BEHAVIORAL_CARD.

The LLM extraction prompt is constrained to *only* the provided line
samples — no training-data lore.
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(__file__))

# ── Sampling keywords for emotional / moral stratum ──────────────────────────
EMOTIONAL_KEYWORDS = [
    "love", "honor", "honour", "duty", "fear", "logic",
    "justice", "sacrifice", "friend", "enemy",
]


# ── Neo4j queries ────────────────────────────────────────────────────────────

def get_top_characters(driver, limit: int = 20) -> list[dict]:
    """
    Top N characters by total line count, with per-series breakdown.
    """
    q_total = """
    MATCH (c:Character)<-[:SPOKEN_BY]-(l:Line)
    WITH c, count(l) AS total
    ORDER BY total DESC
    LIMIT $limit
    RETURN c.canonical_name AS name, total
    """
    q_breakdown = """
    MATCH (c:Character {canonical_name:$name})<-[:SPOKEN_BY]-(l:Line)
    MATCH (e:Episode {id: l.episode_id})
    RETURN e.series AS series, count(l) AS lc
    ORDER BY lc DESC
    """
    out: list[dict] = []
    with driver.session() as s:
        rows = list(s.run(q_total, limit=limit))
        for r in rows:
            name = r["name"]
            br = list(s.run(q_breakdown, name=name))
            out.append({
                "canonical_name": name,
                "total_lines": r["total"],
                "series_breakdown": {x["series"]: x["lc"] for x in br},
            })
    return out


def sample_lines_for_character(driver, name: str, sample_size: int = 200) -> list[dict]:
    """
    Stratified sampling:
        50% longest substantive lines (top 200 by length)
        30% random lines
        20% lines containing emotional/moral keywords
    """
    n_long  = int(sample_size * 0.50)
    n_rand  = int(sample_size * 0.30)
    n_emo   = sample_size - n_long - n_rand

    # Longest 200 speeches (by text length)
    q_long = """
    MATCH (c:Character {canonical_name:$name})<-[:SPOKEN_BY]-(l:Line)
    MATCH (e:Episode {id: l.episode_id})
    WITH l, e, size(l.text) AS len
    ORDER BY len DESC
    LIMIT 200
    WITH l, e ORDER BY rand() LIMIT $n
    RETURN l.text AS text, l.parenthetical AS paren,
           e.title AS title, e.stardate AS stardate
    """

    # Random sample
    q_rand = """
    MATCH (c:Character {canonical_name:$name})<-[:SPOKEN_BY]-(l:Line)
    MATCH (e:Episode {id: l.episode_id})
    WITH l, e, rand() AS r
    ORDER BY r
    LIMIT $n
    RETURN l.text AS text, l.parenthetical AS paren,
           e.title AS title, e.stardate AS stardate
    """

    # Emotional/moral keyword lines
    kw_regex = "(?i).*\\b(" + "|".join(EMOTIONAL_KEYWORDS) + ")\\b.*"
    q_emo = """
    MATCH (c:Character {canonical_name:$name})<-[:SPOKEN_BY]-(l:Line)
    WHERE l.text =~ $rx
    MATCH (e:Episode {id: l.episode_id})
    WITH l, e ORDER BY rand() LIMIT $n
    RETURN l.text AS text, l.parenthetical AS paren,
           e.title AS title, e.stardate AS stardate
    """

    def _rows(session, q, **params):
        return [{
            "text": r["text"],
            "parenthetical": r["paren"],
            "episode_title": r["title"],
            "stardate": r["stardate"],
        } for r in session.run(q, **params)]

    with driver.session() as s:
        long_rows = _rows(s, q_long, name=name, n=n_long)
        rand_rows = _rows(s, q_rand, name=name, n=n_rand)
        emo_rows  = _rows(s, q_emo,  name=name, n=n_emo, rx=kw_regex)

    # Dedup by text while preserving order
    seen = set()
    out = []
    for r in long_rows + emo_rows + rand_rows:
        key = r["text"]
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


# ── LLM extraction ───────────────────────────────────────────────────────────

EXTRACTION_SYSTEM = """You are a careful textual analyst building character
"behavioral cards" for a Star Trek dialogue-grounded chatbot. You will
analyze ONLY the dialogue samples provided and derive observations strictly
from them. Do NOT use prior knowledge of Star Trek, the actors, the
character's biography, or fan lore — even if you recognize the character.
Your job is empirical: what does this corpus of lines reveal?

Output a SINGLE JSON object and nothing else. No markdown fences, no prose
commentary."""

EXTRACTION_USER_TEMPLATE = """Character canonical name: {name}

Below are {n_lines} dialogue lines spoken by this character, drawn from
canon scripts. Some include stage directions in (parentheses). Format:

  [Episode Title | stardate] (paren) "line text"

----- BEGIN DIALOGUE SAMPLES -----
{lines_block}
----- END DIALOGUE SAMPLES -----

Produce a JSON object with EXACTLY these keys:

{{
  "canonical_name": "{name}",
  "model_version": "{model}",
  "core_identity": "2-4 sentence prose summary of who this character is, as
                    revealed by the dialogue (role, temperament, worldview).
                    Cite tendencies, not biography facts.",
  "driving_question": "ONE sentence capturing the moral/philosophical
                       question this character seems to be working through
                       across the samples.",
  "speech_patterns": [
    "5-10 concrete observations about HOW they talk: vocabulary, rhythm,
     contractions, register, syntax, recurring rhetorical moves. Quote
     short fragments as evidence where useful."
  ],
  "decision_heuristics": [
    "5-8 rules-of-thumb this character appears to use when making choices,
     phrased as imperative heuristics. Ground each in what the lines show."
  ],
  "hard_limits": [
    "3-6 things this character refuses to do or strongly resists, as
     evidenced by the dialogue. Phrase as 'Will not ...' / 'Refuses to ...'."
  ],
  "signature_phrases": [
    "5-12 verbatim short phrases or sentence fragments the character
     actually uses (must appear in the samples). Common commands, oaths,
     verbal tics, exclamations. Keep each under ~6 words."
  ],
  "emotional_range": "2-3 sentence description of the emotional bandwidth:
                      what emotions they express, how openly, what they
                      suppress.",
  "intellectual_style": "2-3 sentence description of how they reason:
                         deductive vs intuitive, technical vs humanistic,
                         literal vs allusive, etc."
}}

Rules:
- All content must be derivable from the provided lines. If the corpus is
  thin on some axis, say so briefly within that field rather than inventing.
- Signature phrases MUST be substrings that appear in the samples above.
- Output ONLY the JSON object."""


def _format_lines(lines: list[dict], max_chars: int = 80_000) -> str:
    parts: list[str] = []
    total = 0
    for li in lines:
        ep = li.get("episode_title") or "?"
        sd = li.get("stardate") or "?"
        paren = li.get("parenthetical")
        paren_s = f" ({paren})" if paren else ""
        text = (li.get("text") or "").replace("\n", " ").strip()
        row = f'[{ep} | {sd}]{paren_s} "{text}"'
        if total + len(row) > max_chars:
            break
        parts.append(row)
        total += len(row) + 1
    return "\n".join(parts)


def extract_behavioral_card(
    client,
    character_name: str,
    lines: list[dict],
    model: str = "claude-sonnet-4-5",
    max_tokens: int = 2000,
) -> tuple[dict, dict]:
    """
    Call Claude to produce a behavioral card.

    Returns (card_dict, usage_dict).
    usage_dict has input_tokens, output_tokens.
    """
    block = _format_lines(lines)
    user = EXTRACTION_USER_TEMPLATE.format(
        name=character_name,
        n_lines=len(lines),
        lines_block=block,
        model=model,
    )

    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=EXTRACTION_SYSTEM,
        messages=[{"role": "user", "content": user}],
    )

    raw = "".join(b.text for b in resp.content if getattr(b, "text", None))
    card = _parse_json_loose(raw)

    # Ensure required fields
    card["canonical_name"] = character_name
    card["model_version"] = model

    usage = {
        "input_tokens":  getattr(resp.usage, "input_tokens", 0),
        "output_tokens": getattr(resp.usage, "output_tokens", 0),
    }
    return card, usage


def _parse_json_loose(text: str) -> dict:
    """Extract first JSON object from a string, tolerating fences."""
    text = text.strip()
    # Strip ```json fences if present
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    # Otherwise grab from first { to last }
    if not text.startswith("{"):
        i = text.find("{")
        j = text.rfind("}")
        if i >= 0 and j > i:
            text = text[i:j + 1]
    return json.loads(text)


# ── Storage ──────────────────────────────────────────────────────────────────

LIST_FIELDS = ("speech_patterns", "decision_heuristics",
               "hard_limits", "signature_phrases")

CARD_CONSTRAINT = (
    "CREATE CONSTRAINT bcard_char IF NOT EXISTS "
    "FOR (b:BehavioralCard) REQUIRE b.canonical_name IS UNIQUE"
)


def ensure_schema(driver) -> None:
    with driver.session() as s:
        s.run(CARD_CONSTRAINT)


def store_behavioral_card(driver, card: dict) -> None:
    """
    MERGE a BehavioralCard node keyed by canonical_name and connect it
    to its Character via HAS_BEHAVIORAL_CARD. List fields are stored as
    JSON strings.
    """
    name = card["canonical_name"]
    props = {
        "canonical_name":     name,
        "model_version":      card.get("model_version", ""),
        "core_identity":      card.get("core_identity", ""),
        "driving_question":   card.get("driving_question", ""),
        "emotional_range":    card.get("emotional_range", ""),
        "intellectual_style": card.get("intellectual_style", ""),
    }
    for f in LIST_FIELDS:
        props[f + "_json"] = json.dumps(card.get(f, []))

    with driver.session() as s:
        s.run(CARD_CONSTRAINT)
        s.run(
            """
            MERGE (b:BehavioralCard {canonical_name:$name})
            SET b += $props
            WITH b
            MATCH (c:Character {canonical_name:$name})
            MERGE (c)-[:HAS_BEHAVIORAL_CARD]->(b)
            """,
            name=name, props=props,
        )


def card_exists(driver, name: str) -> bool:
    with driver.session() as s:
        r = s.run(
            "MATCH (b:BehavioralCard {canonical_name:$name}) RETURN count(b) AS n",
            name=name,
        ).single()
        return bool(r and r["n"] > 0)
