#!/usr/bin/env python3
"""
src/episode_writer.py — Multi-agent writer's room for generating
canon-faithful Star Trek episodes.

Architecture (all agents share the same graph as canon bible):

    ┌────────────────┐   premise + series
    │   Showrunner   │ ────────────────────────────────────────┐
    └────────────────┘                                          │
            │ outline (4-6 scenes)                              │
            ▼                                                   │
    ┌────────────────┐                                          │
    │ Canon Validator│  flags violations vs. graph              │
    └───┬────────────┘                                          │
        │ approved outline                                       │
        ▼                                                       │
    ┌────────────────┐  per scene:                              │
    │  Scene Writer  │  + retrieve top-k lines per character    │
    │  (one per      │  + load behavioral card per character    │
    │   scene)       │  + write scene as proper teleplay        │
    └────────────────┘                                          │
            │ N scenes                                          │
            ▼                                                   │
    ┌────────────────┐                                          │
    │   Director     │  assembles scenes, smooths transitions,  │
    │                │  adds opening/closing log entries        │
    └───┬────────────┘                                          │
        │                                                       │
        ▼                                                       │
    ┌────────────────┐                                          │
    │  Final episode │  saved to data/generated_episodes/       │
    └────────────────┘ ◄────────────────────────────────────────┘

Cost target: roughly $0.50-$1.50 per episode at Opus pricing.

Usage:
    python src/episode_writer.py --premise "Picard discovers a derelict
        ship containing the consciousness of an extinct civilization"
        --series TNG --characters PICARD,RIKER,DATA,WORF --scenes 5
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import warnings
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(__file__))
from auth import get_api_key                                          # noqa: E402
from config import (                                                  # noqa: E402
    DEFAULT_LLM_MODEL, __version__,
)

# ── Config ────────────────────────────────────────────────────────────────────

OPUS_MODEL   = "claude-opus-4-5"
SONNET_MODEL = "claude-sonnet-4-5"

# Cost knobs — adjust if you want longer/shorter scenes
OUTLINE_MAX_TOKENS  = 2000
SCENE_MAX_TOKENS    = 2500
DIRECTOR_MAX_TOKENS = 3000
VALIDATOR_MAX_TOKENS = 1500

ROOT = Path(__file__).parent.parent
EPISODES_DIR = ROOT / "data" / "generated_episodes"


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class SceneSpec:
    number: int
    setting: str               # e.g. "Bridge of the Enterprise"
    time_of_day: str           # e.g. "Day"
    characters: list[str]      # canonical names present
    summary: str               # 2-3 sentence summary
    purpose: str               # what the scene accomplishes in the story
    written_text: str = ""     # filled in by Scene Writer


@dataclass
class EpisodeOutline:
    title: str
    series: str
    teaser_premise: str        # 1 sentence
    logline: str               # 1-2 sentence pitch
    central_dilemma: str       # the moral question
    a_plot: str
    b_plot: str
    scenes: list[SceneSpec]
    canon_warnings: list[str] = field(default_factory=list)


# ── LLM helper ────────────────────────────────────────────────────────────────

def call_llm(client, *, system, messages, model=OPUS_MODEL, max_tokens=2000):
    """Single Anthropic call. Returns (text, usage)."""
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    )
    text = next(b.text for b in response.content if hasattr(b, "text"))
    return text, response.usage


# ── Graph helpers ─────────────────────────────────────────────────────────────

def get_character_packets(retriever, character_names: list[str], series: str) -> dict:
    """For each character: behavioral card + a small set of representative lines."""
    packets = {}
    for name in character_names:
        name = name.upper()
        card = retriever.get_character_card(name)
        if not card["total_lines"]:
            print(f"  ! warning: {name} not found in graph", file=sys.stderr)
            continue
        # Generic sampling — pull some lines about "duty and command" as default seed
        lines = retriever.search_lines(name, "duty command starship mission",
                                       top_k=12, series=series)
        packets[name] = {
            "card": card,
            "seed_lines": lines,
        }
    return packets


# ── Showrunner: produce episode outline ───────────────────────────────────────

SHOWRUNNER_PROMPT = """You are the SHOWRUNNER for a new Star Trek episode in the {series} series.

You'll receive a premise and a roster of characters. Your job: produce a
tightly structured outline as a single JSON object matching this schema:

{{
  "title":            "...",
  "logline":          "1-2 sentence pitch",
  "central_dilemma":  "the moral question driving the episode",
  "a_plot":           "main story arc (3-4 sentences)",
  "b_plot":           "secondary character story (2-3 sentences)",
  "scenes": [
    {{
      "number":       1,
      "setting":      "Bridge of the Enterprise",
      "time_of_day":  "Day",
      "characters":   ["PICARD", "RIKER", "DATA"],
      "summary":      "2-3 sentence scene summary",
      "purpose":      "what this scene accomplishes in the story"
    }},
    ...
  ]
}}

Constraints:
- Exactly {scene_count} scenes.
- Stay tonally consistent with {series}:
  {series_profile}
- Use only the provided characters. Do not invent senior officers
  beyond those listed.
- Honor canon: no major character deaths, no Prime Directive violations
  presented as heroic, no permanent universe-altering events.
- End on a note appropriate to the series (TNG: philosophical resolution,
  DS9: moral complexity preserved, TOS: confident frontier optimism).

RESPOND WITH ONLY THE JSON OBJECT — no preamble, no markdown fence.
"""

SERIES_PROFILES = {
    "TNG": ("Enlightened humanism, diplomacy before force, philosophical "
            "introspection. Most episodes resolve with a moral insight. "
            "Setting: USS Enterprise-D, exploration era. Tone: aspirational, "
            "measured, intellectual."),
    "DS9": ("Moral complexity, lived-in setting, ensemble cast. Episodes "
            "may end ambiguously. War, religion, and political grayness "
            "are central. Setting: Deep Space Nine station near Bajor. "
            "Tone: serialized, mature, willing to break Federation idealism."),
    "TOS": ("Frontier optimism, big philosophical allegory, action-driven. "
            "Episodes typically resolve cleanly with humanist victory. "
            "Setting: USS Enterprise NCC-1701, 5-year mission. "
            "Tone: confident, theatrical, bold."),
}


def write_outline(client, *, premise: str, series: str,
                  characters: list[str], scene_count: int):
    profile = SERIES_PROFILES.get(series.upper(), SERIES_PROFILES["TNG"])
    system = SHOWRUNNER_PROMPT.format(
        series=series.upper(),
        scene_count=scene_count,
        series_profile=profile,
    )
    user = (
        f"PREMISE: {premise}\n\n"
        f"AVAILABLE CHARACTERS: {', '.join(characters)}\n\n"
        f"Produce the outline JSON now."
    )
    text, usage = call_llm(client, system=system,
                            messages=[{"role": "user", "content": user}],
                            model=OPUS_MODEL,
                            max_tokens=OUTLINE_MAX_TOKENS)

    # Robust JSON extraction (in case the model wraps it in a fence)
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()
    if not text.startswith("{"):
        # Try to find the first { ... }
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start:end + 1]
    data = json.loads(text)

    scenes = [SceneSpec(**{k: v for k, v in s.items()
                            if k in SceneSpec.__dataclass_fields__})
              for s in data.get("scenes", [])]
    return EpisodeOutline(
        title=data["title"],
        series=series.upper(),
        teaser_premise=premise,
        logline=data["logline"],
        central_dilemma=data["central_dilemma"],
        a_plot=data["a_plot"],
        b_plot=data.get("b_plot", ""),
        scenes=scenes,
    ), usage


# ── Canon Validator ───────────────────────────────────────────────────────────

VALIDATOR_PROMPT = """You are the CANON VALIDATOR for a Star Trek episode outline.

You'll receive an outline and a roster of characters with their canonical
profiles. Your job: spot continuity or characterization violations that
would break the {series} canon.

Output a JSON object:
{{
  "approve":    true|false,
  "warnings":   ["list", "of", "issues"],
  "suggestions": ["specific fixes"]
}}

Be strict but practical. Focus on real continuity issues:
- Character acting drastically out of canon (e.g. Picard ordering torture)
- Plot relying on tech the era doesn't have (e.g. holographic doctor in TOS)
- Cultural/political contradictions (e.g. Klingons honoring an unauthorized treaty)
- Universe-altering events that would require multi-episode setup

Do NOT flag minor stuff (e.g. unusual word choice, novel philosophical angle).

RESPOND WITH ONLY THE JSON.
"""


def validate_outline(client, outline: EpisodeOutline,
                     packets: dict) -> tuple[bool, list[str], list[str], object]:
    cards_summary = []
    for name, p in packets.items():
        bc = p["card"].get("behavioral_card") or {}
        cards_summary.append(
            f"{name}: {bc.get('core_identity', 'no card')[:200]}"
        )

    user = (
        f"SERIES: {outline.series}\n"
        f"TITLE: {outline.title}\n"
        f"LOGLINE: {outline.logline}\n"
        f"CENTRAL DILEMMA: {outline.central_dilemma}\n"
        f"A-PLOT: {outline.a_plot}\n"
        f"B-PLOT: {outline.b_plot}\n\n"
        f"SCENES:\n" +
        "\n".join(f"  {s.number}. [{s.setting}] {s.summary}"
                  for s in outline.scenes) +
        f"\n\nCHARACTER PROFILES:\n" + "\n".join(cards_summary)
    )

    system = VALIDATOR_PROMPT.format(series=outline.series)
    text, usage = call_llm(client, system=system,
                            messages=[{"role": "user", "content": user}],
                            model=SONNET_MODEL,
                            max_tokens=VALIDATOR_MAX_TOKENS)
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    data = json.loads(text)
    return (bool(data.get("approve", True)),
            data.get("warnings", []),
            data.get("suggestions", []),
            usage)


# ── Scene Writer ──────────────────────────────────────────────────────────────

SCENE_WRITER_PROMPT = """You are the SCENE WRITER for Scene {number} of a {series} episode.

You will write the scene in proper Star Trek teleplay format:

  INT./EXT. LOCATION - TIME OF DAY

      (Brief action / staging description.)

      CHARACTER NAME
                (parenthetical, if any)
          Dialogue line.

      (More action between dialogue blocks as needed.)

Constraints:
- Stay tonally consistent with {series}.
- Use ONLY the characters listed for this scene.
- Each character must speak in voice — see their BEHAVIORAL PROFILE below.
- Dialogue must feel authentic — short bursts, not monologues, unless the
  character is delivering a moment of weight.
- Aim for ~3-5 pages of dialogue/action (roughly 40-70 lines of dialogue).
- End the scene at a natural beat, not mid-conversation.

DO NOT include scene headers like "SCENE {number}" — start directly with
the location/INT-EXT header. DO NOT include camera directions.

CHARACTERS IN THIS SCENE:

{character_blocks}

SCENE SPECIFICATION:
  Setting:     {setting}
  Time of day: {time_of_day}
  Summary:     {summary}
  Purpose:     {purpose}

CONTEXT — the episode this scene belongs to:
  Title:            {ep_title}
  Logline:          {logline}
  Central dilemma:  {dilemma}
  A-plot:           {a_plot}

Write the scene now.
"""


def _format_character_block(name: str, packet: dict) -> str:
    card = packet["card"]
    bc = card.get("behavioral_card") or {}
    lines_seed = packet.get("seed_lines", [])
    out = [f"  ┌─ {name} ──────────────────────────────"]
    if bc.get("core_identity"):
        out.append(f"  │ Core: {bc['core_identity']}")
    if bc.get("speech_patterns_json"):
        try:
            sp = json.loads(bc["speech_patterns_json"])
            if sp:
                out.append(f"  │ Speech patterns:")
                for p in sp[:5]:
                    out.append(f"  │   - {p}")
        except Exception:
            pass
    if bc.get("signature_phrases_json"):
        try:
            sigs = json.loads(bc["signature_phrases_json"])
            if sigs:
                out.append(f"  │ Signature phrases: " +
                           ", ".join(f'"{s}"' for s in sigs[:6]))
        except Exception:
            pass
    if lines_seed:
        out.append(f"  │ Representative canon lines:")
        for l in lines_seed[:5]:
            out.append(f"  │   • {l['text'][:140]}")
    out.append("  └──────────────────────────────────────")
    return "\n".join(out)


def write_scene(client, scene: SceneSpec, outline: EpisodeOutline,
                packets: dict) -> tuple[str, object]:
    chars_in_scene = [c for c in scene.characters if c in packets]
    blocks = "\n\n".join(_format_character_block(c, packets[c])
                          for c in chars_in_scene)
    system = SCENE_WRITER_PROMPT.format(
        number=scene.number,
        series=outline.series,
        character_blocks=blocks,
        setting=scene.setting,
        time_of_day=scene.time_of_day,
        summary=scene.summary,
        purpose=scene.purpose,
        ep_title=outline.title,
        logline=outline.logline,
        dilemma=outline.central_dilemma,
        a_plot=outline.a_plot,
    )
    user = f"Write Scene {scene.number} of the episode now."
    text, usage = call_llm(client, system=system,
                            messages=[{"role": "user", "content": user}],
                            model=OPUS_MODEL,
                            max_tokens=SCENE_MAX_TOKENS)
    return text.strip(), usage


# ── Director: stitch scenes into final teleplay ───────────────────────────────

DIRECTOR_PROMPT = """You are the DIRECTOR. You receive a complete Star Trek
teleplay broken into scenes by separate writers. Your output will be a
COMPACT JSON object — not the full teleplay.

Your job is to produce structural metadata only:

{{
  "act_breaks":  [2, 4],
  "tag_scene":   "A short epilogue scene (1 paragraph) appropriate to {series_name} - takes place after the final written scene. Include a setting, 2-3 characters, and 3-6 lines of dialogue that resolve the central dilemma's emotional thread.",
  "teaser_voiceover": "A Captain's Log voiceover (1 paragraph, ~80 words) introducing the episode's setting and stakes. Should sound like the captain of this series."
}}

The "act_breaks" array lists scene numbers AFTER which an Act break should
appear (e.g. [2, 4] means insert ACT II after scene 2 and ACT III after
scene 4). Use TNG/DS9-style 4-act structure (3 breaks for a 5-scene episode).

The "tag_scene" should be a SHORT (max 250 words) epilogue scene written
in the same teleplay format as the input scenes.

Do NOT rewrite or summarize the input scenes. Just produce structural
metadata.

RESPOND WITH ONLY THE JSON OBJECT.
"""


def stitch_episode(client, outline: EpisodeOutline,
                   scenes_text: list[str]) -> tuple[str, object]:
    """Director produces structural metadata (much cheaper) and we stitch
    the final teleplay in Python — guaranteeing no scene content is lost."""
    series_name = {
        "TNG": "STAR TREK: THE NEXT GENERATION",
        "DS9": "STAR TREK: DEEP SPACE NINE",
        "TOS": "STAR TREK",
    }.get(outline.series, "STAR TREK")

    # Tell director about the scenes (summaries only, not full text)
    scene_blurbs = "\n".join(
        f"Scene {s.number}: [{s.setting}] {s.summary}"
        for s in outline.scenes
    )

    user = (
        f"TITLE: {outline.title}\n"
        f"SERIES: {series_name}\n"
        f"LOGLINE: {outline.logline}\n"
        f"CENTRAL DILEMMA: {outline.central_dilemma}\n\n"
        f"SCENES (summaries only):\n{scene_blurbs}\n\n"
        f"Produce the structural metadata JSON now."
    )

    text, usage = call_llm(
        client,
        system=DIRECTOR_PROMPT.format(series_name=series_name),
        messages=[{"role": "user", "content": user}],
        model=SONNET_MODEL,     # Cheaper — director just does metadata now
        max_tokens=DIRECTOR_MAX_TOKENS,
    )

    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    meta = json.loads(text)

    act_breaks = set(meta.get("act_breaks", []))
    tag_scene = (meta.get("tag_scene") or "").strip()
    teaser_vo = (meta.get("teaser_voiceover") or "").strip()

    # Now stitch in Python — preserves every character of the scene texts.
    out = []
    out.append(f"**{series_name}**\n")
    out.append(f"\n\"{outline.title}\"\n")
    out.append(f"\nWritten by the Writers' Room\n")
    out.append(f"Based on STAR TREK created by Gene Roddenberry\n")
    out.append(f"\n---\n")

    if teaser_vo:
        out.append("\nTEASER\n")
        out.append("\nFADE IN:\n")
        out.append(f"\n{teaser_vo}\n")
        out.append("\nFADE OUT.\n")
        out.append("\n---\n")

    current_act = 1
    out.append(f"\n**ACT {_roman(current_act)}**\n")
    out.append("\nFADE IN:\n")

    for i, scene in enumerate(outline.scenes, start=1):
        out.append("\n")
        out.append(scenes_text[i - 1])
        out.append("\n")
        if i in act_breaks and i < len(outline.scenes):
            current_act += 1
            out.append(f"\nEND OF ACT {_roman(current_act - 1)}\n")
            out.append("\n---\n")
            out.append(f"\n**ACT {_roman(current_act)}**\n")
            out.append("\nFADE IN:\n")

    out.append(f"\nEND OF ACT {_roman(current_act)}\n")
    out.append("\n---\n")

    if tag_scene:
        out.append("\nTAG\n")
        out.append("\nFADE IN:\n")
        out.append(f"\n{tag_scene}\n")
        out.append("\nFADE OUT.\n")

    out.append("\n---\n")
    out.append("\nEND OF SHOW\n")

    return "".join(out), usage


def _roman(n: int) -> str:
    return ["", "I", "II", "III", "IV", "V", "VI"][n] if 0 <= n <= 6 else str(n)


# ── Persistence ───────────────────────────────────────────────────────────────

def save_episode(outline: EpisodeOutline, final_text: str,
                 metadata: dict) -> Path:
    EPISODES_DIR.mkdir(parents=True, exist_ok=True)
    slug = (outline.title.lower()
             .replace(" ", "_")
             .replace("'", "")
             .replace("\"", "")
             .replace(":", "")
             .replace("/", "_"))
    ts = time.strftime("%Y%m%d-%H%M")
    base = EPISODES_DIR / f"{ts}-{outline.series.lower()}-{slug}"

    # Teleplay text
    teleplay = base.with_suffix(".txt")
    teleplay.write_text(final_text, encoding="utf-8")

    # Sidecar metadata + outline
    payload = {
        "metadata":  metadata,
        "outline":   asdict(outline),
    }
    sidecar = base.with_suffix(".json")
    sidecar.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    return teleplay


# ── Orchestration ─────────────────────────────────────────────────────────────

def write_episode(args) -> int:
    import anthropic
    from retriever import Retriever, EmptyCollectionError

    print(f"\n╔══════════════════════════════════════════════════════════╗")
    print(f"║  Star Trek Episode Writer · v{__version__}                    ║")
    print(f"║  Series:  {args.series:<10}                                 ║")
    print(f"║  Scenes:  {args.scenes:<2}                                          ║")
    print(f"║  Characters: {', '.join(args.characters[:6]):<44} ║")
    print(f"╚══════════════════════════════════════════════════════════╝\n")

    print(f"PREMISE:\n  {args.premise}\n")

    try:
        client = anthropic.Anthropic(api_key=get_api_key())
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr); return 1

    try:
        retriever = Retriever()
    except EmptyCollectionError as exc:
        print(str(exc), file=sys.stderr); return 1

    cumulative_in, cumulative_out = 0, 0

    # ── Step 1: Showrunner outline ─────────────────────────────────────────
    print("→ [Showrunner] writing outline...")
    t0 = time.time()
    outline, usage = write_outline(
        client,
        premise=args.premise,
        series=args.series,
        characters=args.characters,
        scene_count=args.scenes,
    )
    cumulative_in += usage.input_tokens
    cumulative_out += usage.output_tokens
    print(f"  ✓ Outline: {outline.title}  ({time.time()-t0:.1f}s, "
          f"{usage.input_tokens}+{usage.output_tokens} tok)")
    print(f"    Logline: {outline.logline}")
    print(f"    Scenes:")
    for s in outline.scenes:
        print(f"      {s.number}. [{s.setting}] {s.summary[:80]}")

    # ── Step 2: Pull character packets from graph ──────────────────────────
    print(f"\n→ Pulling character profiles from graph...")
    packets = get_character_packets(retriever, args.characters, args.series)
    print(f"  ✓ Loaded {len(packets)} character packets "
          f"(behavioral card + seed lines)")

    # ── Step 3: Canon validation ───────────────────────────────────────────
    print(f"\n→ [Canon Validator] checking outline...")
    t0 = time.time()
    approve, warnings_, suggestions, usage = validate_outline(client, outline, packets)
    cumulative_in += usage.input_tokens
    cumulative_out += usage.output_tokens
    outline.canon_warnings = warnings_
    status = "✓ APPROVED" if approve else "⚠ FLAGGED"
    print(f"  {status}  ({time.time()-t0:.1f}s, "
          f"{usage.input_tokens}+{usage.output_tokens} tok)")
    for w in warnings_[:5]:
        print(f"    ! {w}")
    for s in suggestions[:5]:
        print(f"    → suggestion: {s}")

    # ── Step 4: Write each scene ───────────────────────────────────────────
    print(f"\n→ [Scene Writers] writing {len(outline.scenes)} scenes...")
    scene_texts = []
    for scene in outline.scenes:
        t0 = time.time()
        print(f"  → Scene {scene.number}: {scene.summary[:60]}...")
        text, usage = write_scene(client, scene, outline, packets)
        cumulative_in += usage.input_tokens
        cumulative_out += usage.output_tokens
        scene.written_text = text
        scene_texts.append(text)
        print(f"    ✓ {len(text)} chars  ({time.time()-t0:.1f}s, "
              f"{usage.input_tokens}+{usage.output_tokens} tok)")

    # ── Step 5: Director stitches final teleplay ──────────────────────────
    print(f"\n→ [Director] stitching final teleplay...")
    t0 = time.time()
    final_text, usage = stitch_episode(client, outline, scene_texts)
    cumulative_in += usage.input_tokens
    cumulative_out += usage.output_tokens
    print(f"  ✓ Final teleplay: {len(final_text)} chars  ({time.time()-t0:.1f}s, "
          f"{usage.input_tokens}+{usage.output_tokens} tok)")

    # ── Step 6: Save ──────────────────────────────────────────────────────
    metadata = {
        "writer_version": __version__,
        "premise":        args.premise,
        "series":         args.series,
        "characters":     args.characters,
        "scenes":         len(outline.scenes),
        "models":         {"showrunner": OPUS_MODEL,
                           "validator": SONNET_MODEL,
                           "scene":     OPUS_MODEL,
                           "director":  OPUS_MODEL},
        "tokens_input":   cumulative_in,
        "tokens_output":  cumulative_out,
    }
    teleplay_path = save_episode(outline, final_text, metadata)
    retriever.close()

    # Sonnet $3/$15 per M, Opus $15/$75 per M.  Rough: most calls were Opus.
    est_cost = (cumulative_in * 15 / 1e6) + (cumulative_out * 75 / 1e6)

    print(f"\n╔══════════════════════════════════════════════════════════╗")
    print(f"║  EPISODE COMPLETE                                         ║")
    print(f"╠══════════════════════════════════════════════════════════╣")
    print(f"║  Title:        {outline.title[:42]:<42} ║")
    print(f"║  Saved to:     {str(teleplay_path)[-42:]:<42} ║")
    print(f"║  Total tokens: in={cumulative_in:>7,}  out={cumulative_out:>7,}        ║")
    print(f"║  Approx cost:  ${est_cost:.2f} (Opus-weighted estimate)         ║")
    print(f"╚══════════════════════════════════════════════════════════╝\n")
    return 0


# ── CLI ───────────────────────────────────────────────────────────────────────

DEFAULT_TNG_CAST = ["PICARD", "RIKER", "DATA", "WORF", "TROI", "BEVERLY", "GEORDI"]
DEFAULT_DS9_CAST = ["SISKO", "KIRA", "ODO", "BASHIR", "DAX", "QUARK", "O'BRIEN", "WORF"]
DEFAULT_TOS_CAST = ["KIRK", "SPOCK", "MCCOY", "SCOTT", "UHURA", "SULU", "CHEKOV"]


def default_cast(series: str) -> list[str]:
    return {"TNG": DEFAULT_TNG_CAST,
            "DS9": DEFAULT_DS9_CAST,
            "TOS": DEFAULT_TOS_CAST}.get(series.upper(), DEFAULT_TNG_CAST)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Generate a canon-faithful Star Trek episode."
    )
    ap.add_argument("--premise", required=True,
                    help="One- or two-sentence premise for the episode.")
    ap.add_argument("--series", default="TNG", choices=["TNG", "TOS", "DS9"],
                    help="Which series to write for (affects tone, characters).")
    ap.add_argument("--characters", default=None,
                    help="Comma-separated list of characters to include "
                         "(default: senior cast for the series).")
    ap.add_argument("--scenes", type=int, default=5,
                    help="Number of scenes to generate (default 5).")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = ap.parse_args()

    args.series = args.series.upper()
    if args.characters:
        args.characters = [c.strip().upper() for c in args.characters.split(",")]
    else:
        args.characters = default_cast(args.series)

    return write_episode(args)


if __name__ == "__main__":
    raise SystemExit(main())
