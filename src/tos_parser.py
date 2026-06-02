#!/usr/bin/env python3
"""TOS transcript parser (chakoteya.net) → structured JSON.

These are HTML transcripts (not screenplays). Format:

  <title>The Star Trek Transcripts - The Trouble With Tribbles</title>
  ...
  <b>The Trouble With Tribbles</b>
  Stardate: 4523.3
  Original Airdate: 29 Dec, 1967
  ...
  <b>[Briefing room]</b>                          ← scene marker
  SPOCK: Deep Space Station K7 now within ...<br>
  KIRK: Good. Mister Chekov ...<br>
  UHURA [OC]: Captain?<br>                        ← speaker modifier
  (Kirk and Spock arrive ...)                     ← stage direction
  Captain's Log, stardate 4523.3 ...              ← narration → KIRK / Log

Output schema matches src/parser.py (TNG screenplay parser) so that
src/loader.py can consume both without changes. Episode IDs are prefixed
"tos:<N>" to avoid colliding with the bare-int TNG ids ("102"..).

Defensive parsing: log warnings, never crash on malformed dialogue. The
only hard failure is "no dialogue lines extracted" — caller wants to see
that.
"""
from __future__ import annotations

import json
import logging
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

from bs4 import BeautifulSoup

log = logging.getLogger("trek.tos_parser")

# ── Regexes ───────────────────────────────────────────────────────────────────

# Speaker cue at start of a line.  Allow optional " [modifier]" between name
# and the colon (e.g. KIRK [OC]:, UHURA [on monitor]:).  Accept ":" or ";"
# (the source has occasional typos like "SPOCK; ...").  Name: 2-25 chars,
# uppercase letters / digits / spaces / apostrophes / hyphens / periods.
RE_CUE = re.compile(
    r"^(?P<name>[A-Z][A-Z0-9'’\-\. ]{1,24}?)"
    r"(?:\s*\[(?P<mod>[^\]]+)\])?"
    r"\s*[:;]\s*"
    r"(?P<text>.*)$"
)

RE_SCENE = re.compile(r"^\s*[\[\]](?P<loc>[^\[\]]+?)[\]\[]\s*$")
RE_STAGE = re.compile(r"^\s*\((?P<text>[^)]+)\)\s*$")
RE_STARDATE = re.compile(r"Stardate[:\s]+([0-9]+\.?[0-9]*)", re.IGNORECASE)
RE_AIRDATE = re.compile(r"Original\s+Airdate[:\s]+([^\n<]+)", re.IGNORECASE)
RE_LOG_PARA = re.compile(r"^(Captain's\s+log|Captain's\s+personal\s+log|"
                         r"Ship's\s+log|First\s+officer's\s+log|"
                         r"Medical\s+log|Personal\s+log)\b",
                         re.IGNORECASE)

# Lines that look like cues but aren't dialogue
NON_CUE = {
    "THE END", "END", "FADE IN", "FADE OUT", "STAR TREK",
}

# Captains by series — used to attribute uncredited Log narration.
CAPTAIN = {"TOS": "KIRK"}


# ── Data ──────────────────────────────────────────────────────────────────────


@dataclass
class Line:
    line_num: int
    speaker: str
    text: str
    parenthetical: str | None = None
    scene_idx: int | None = None


@dataclass
class Scene:
    scene_idx: int
    number: str | None
    heading: str
    int_ext: str | None
    location: str | None
    act: str | None


@dataclass
class ParsedScript:
    id: str
    series: str = "TOS"
    source_type: str = "transcript"
    title: str | None = None
    writer: str | None = None
    director: str | None = None
    stardate: str | None = None
    airdate: str | None = None
    production_code: str | None = None
    characters: list[dict] = field(default_factory=list)
    scenes: list[Scene] = field(default_factory=list)
    lines: list[Line] = field(default_factory=list)
    ships: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _clean_speaker(name: str) -> str:
    name = name.strip().rstrip(":;").strip()
    name = re.sub(r"\s+", " ", name)
    return name


def _is_valid_speaker(name: str) -> bool:
    if not name or len(name) < 2 or len(name) > 25:
        return False
    if name in NON_CUE:
        return False
    if not re.search(r"[A-Z]", name):
        return False
    # Must be mostly uppercase letters (allow spaces/dots/etc but at least one A-Z)
    letters = [c for c in name if c.isalpha()]
    if not letters:
        return False
    if sum(1 for c in letters if c.isupper()) / len(letters) < 0.8:
        return False
    return True


def _html_to_text(html: str) -> str:
    """Convert chakoteya HTML to a clean line-oriented text stream.

    - <br> and </p> become hard newlines (these are the line separators in
      the source markup; without this every speaker line gets joined into
      one giant paragraph).
    - <b>[scene]</b> stays on its own line.
    - All other tags are stripped.
    """
    # Normalise <br> variants to newlines BEFORE BS4 collapses whitespace.
    html = re.sub(r"<\s*br\s*/?\s*>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"</\s*p\s*>", "\n\n", html, flags=re.IGNORECASE)
    html = re.sub(r"</\s*tr\s*>", "\n", html, flags=re.IGNORECASE)
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n")
    # Collapse runs of blank lines, normalise CRLF, trim trailing spaces.
    text = text.replace("\r", "")
    lines = [ln.rstrip() for ln in text.split("\n")]
    out: list[str] = []
    prev_blank = False
    for ln in lines:
        if not ln.strip():
            if not prev_blank:
                out.append("")
            prev_blank = True
        else:
            out.append(ln)
            prev_blank = False
    return "\n".join(out)


def _extract_title(html: str, text: str) -> str | None:
    # Prefer <title>The Star Trek Transcripts - Foo</title>
    m = re.search(r"<title>([^<]+)</title>", html, re.IGNORECASE)
    if m:
        t = m.group(1).strip()
        t = re.sub(r"^\s*The\s+Star\s+Trek\s+Transcripts\s*[-–:]\s*", "", t,
                   flags=re.IGNORECASE)
        t = re.sub(r"\s+", " ", t).strip(" -–:\"'")
        if t and len(t) < 100:
            return t
    # Fallback: first non-empty line of the cleaned text body
    for ln in text.split("\n")[:20]:
        s = ln.strip()
        if not s:
            continue
        if RE_STARDATE.search(s) or RE_AIRDATE.search(s):
            continue
        if len(s) < 80 and not s.endswith(":"):
            return s
    return None


def _glue_continuation(text: str) -> str:
    """The source wraps long dialogue mid-sentence with bare `<br>`-
    separated lines.  After our `<br>` → `\\n` conversion, those become
    distinct lines that look like orphan text (no SPEAKER:).

    We join any line that does NOT start with a cue/scene/stage marker
    onto the previous line.  Blank lines stay as paragraph breaks.
    """
    out: list[str] = []
    for raw in text.split("\n"):
        ln = raw.strip()
        if not ln:
            out.append("")
            continue
        if (RE_CUE.match(ln) or RE_SCENE.match(ln) or RE_STAGE.match(ln)
                or RE_LOG_PARA.match(ln)):
            out.append(ln)
        else:
            # continuation of previous non-empty line
            if out and out[-1].strip():
                out[-1] = out[-1] + " " + ln
            else:
                out.append(ln)
    return "\n".join(out)


# ── Main parse ────────────────────────────────────────────────────────────────


def parse_transcript(prod_num: str, html: str) -> ParsedScript:
    ps = ParsedScript(id=f"tos:{prod_num}")

    text = _html_to_text(html)
    ps.title = _extract_title(html, text)
    if m := RE_STARDATE.search(text[:2000]):
        ps.stardate = m.group(1)
    if m := RE_AIRDATE.search(text[:2000]):
        ps.airdate = m.group(1).strip().rstrip(",;")

    text = _glue_continuation(text)

    scene_counter = 0
    line_counter = 0
    cur_scene: Scene | None = None
    pending_paren: list[str] = []
    seen_chars: dict[str, dict] = {}
    locations_seen: set[str] = set()
    ships_seen: set[str] = set()
    captain = CAPTAIN.get("TOS", "KIRK")

    for raw in text.split("\n"):
        ln = raw.strip()
        if not ln:
            continue

        # Scene marker — `[Location]`.  The source occasionally typos one
        # bracket as the wrong direction (`]Bridge]`), so RE_SCENE accepts
        # either bracket on each side.
        m = RE_SCENE.match(ln)
        if m:
            loc = m.group("loc").strip()
            # Reject things that are actually stage directions in brackets
            # (rare here, but defensive).
            if loc and len(loc) < 80:
                scene_counter += 1
                cur_scene = Scene(
                    scene_idx=scene_counter,
                    number=None,
                    heading=loc,
                    int_ext=None,
                    location=loc,
                    act=None,
                )
                ps.scenes.append(cur_scene)
                locations_seen.add(loc)
                pending_paren.clear()
                continue

        # Stage direction (parens) — attach to next dialogue line
        m = RE_STAGE.match(ln)
        if m:
            pending_paren.append(m.group("text").strip())
            continue

        # Captain's Log narration — no SPEAKER: prefix in source
        if RE_LOG_PARA.match(ln):
            line_counter += 1
            li = Line(
                line_num=line_counter,
                speaker=captain,
                text=ln,
                parenthetical="Log",
                scene_idx=cur_scene.scene_idx if cur_scene else None,
            )
            ps.lines.append(li)
            ch = seen_chars.setdefault(
                captain,
                {"canonical_name": captain, "first_line": line_counter,
                 "line_count": 0},
            )
            if ch["first_line"] is None:
                ch["first_line"] = line_counter
            ch["line_count"] += 1
            pending_paren.clear()
            continue

        # Speaker cue
        m = RE_CUE.match(ln)
        if m:
            name = _clean_speaker(m.group("name"))
            if not _is_valid_speaker(name):
                continue
            text_body = m.group("text").strip()
            mod = m.group("mod")
            # Inline stage directions inside the dialogue, e.g.
            #   "KIRK: What? (Lurry hands him a packet) Wheat. So what?"
            # We keep the text verbatim — stripping in-line parens would
            # mangle readable dialogue.  pending_paren from preceding
            # bare-parens lines is folded into parenthetical instead.
            parts = [p for p in [mod] + pending_paren if p]
            paren = "; ".join(parts) if parts else None
            pending_paren.clear()
            if not text_body:
                # Cue with no dialogue body (rare typo) — skip
                continue
            line_counter += 1
            li = Line(
                line_num=line_counter,
                speaker=name,
                text=text_body,
                parenthetical=paren,
                scene_idx=cur_scene.scene_idx if cur_scene else None,
            )
            ps.lines.append(li)
            ch = seen_chars.setdefault(
                name,
                {"canonical_name": name, "first_line": line_counter,
                 "line_count": 0},
            )
            if ch["first_line"] is None:
                ch["first_line"] = line_counter
            ch["line_count"] += 1
            continue

        # Unrecognised non-blank line — ignore (was likely action/narration
        # the continuation-glue couldn't attach).  Don't warn per-line; too
        # noisy.

    # Ship detection (very light Layer-1 seed)
    body_upper = text.upper()
    if "ENTERPRISE" in body_upper:
        ships_seen.add("Enterprise")

    ps.characters = sorted(seen_chars.values(), key=lambda c: -c["line_count"])
    ps.locations = sorted(locations_seen)
    ps.ships = sorted(ships_seen)

    if not ps.title:
        ps.warnings.append("Title not detected")
    if not ps.scenes:
        ps.warnings.append("No scenes detected")
    if not ps.lines:
        # Hard failure — caller wants to see this
        raise ValueError(f"{ps.id}: no dialogue lines extracted")
    return ps


# ── Public API ────────────────────────────────────────────────────────────────


def to_dict(ps: ParsedScript) -> dict:
    return asdict(ps)


def parse_file(path: Path) -> ParsedScript:
    """Parse a chakoteya HTML file. Production number is taken from the
    filename stem, accepting either `tos_42.htm` or bare `42.htm`."""
    stem = path.stem
    if stem.startswith("tos_"):
        prod = stem[4:]
    else:
        prod = stem
    html = path.read_text(encoding="utf-8", errors="replace")
    return parse_transcript(prod, html)


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s %(message)s")
    root = Path(__file__).resolve().parents[1]
    raw_dir = root / "data" / "raw"
    out_dir = root / "data" / "parsed"
    out_dir.mkdir(parents=True, exist_ok=True)

    files = [Path(a) for a in argv] if argv else sorted(raw_dir.glob("tos_*.htm*"))
    for f in files:
        if not f.exists():
            log.error("missing: %s", f)
            continue
        try:
            ps = parse_file(f)
        except Exception as e:
            log.error("%s: %s", f.name, e)
            continue
        out = out_dir / f"{ps.id.replace(':', '_')}.json"
        out.write_text(json.dumps(to_dict(ps), indent=2, ensure_ascii=False))
        print(f"[parse] {ps.id}: title={ps.title!r:40s} "
              f"scenes={len(ps.scenes):3d} lines={len(ps.lines):4d} "
              f"chars={len(ps.characters):3d} warn={len(ps.warnings)}")
        for w in ps.warnings:
            log.warning("  %s: %s", ps.id, w)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
