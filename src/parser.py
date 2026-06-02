#!/usr/bin/env python3
"""Parse st-minutiae screenplay text into structured JSON.

These are classic screenplay format scripts:
  - Numbered scene headings (e.g. "1    EXT. SPACE - STARSHIP")
  - Character cues in ALL CAPS, deeply indented
  - Optional parenthetical on next line
  - Dialogue lines indented under the cue
  - Action lines start with a tab/spaces but contain mixed case

We extract: title, writer, stardate, characters, scenes, dialogue lines.
Defensive: log warnings but never crash; emit partial JSON.
"""
from __future__ import annotations

import json
import logging
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable

log = logging.getLogger("trek.parser")

# ---- Regexes -----------------------------------------------------------------

# Scene heading: optional leading number, then INT./EXT. and description.
RE_SCENE_HEADER = re.compile(
    r"^\s*(?P<num>\d+[A-Z]?)?\s*(?P<head>(?:INT\.|EXT\.|INT\.?/EXT\.?|EXT\.?/INT\.?)[^\n]+)$"
)
# Pure scene-number continuation lines like "7    CONTINUED:"
RE_CONTINUED = re.compile(r"^\s*\d+[A-Z]?\s+CONTINUED[: ]*\(?\d*\)?\s*$", re.IGNORECASE)
# Act / teaser markers
RE_ACT = re.compile(r"^\s*(TEASER|ACT\s+(?:ONE|TWO|THREE|FOUR|FIVE|SIX|[IVX]+|\d+)|TAG)\s*$")
# Character cue: highly indented all-caps single line (optionally V.O./O.S./CONT'D).
RE_CUE = re.compile(
    r"^(?P<indent>\t+|[ ]{16,})"
    r"(?P<name>[A-Z][A-Z0-9'’\-\. ]{1,30}?)"
    r"(?:\s*\((?P<paren>[^)]+)\))?\s*$"
)
# Stuff that can appear as ALL CAPS but isn't a cue
NON_CUE = {
    "FADE IN", "FADE OUT", "CUT TO", "DISSOLVE TO", "SMASH CUT",
    "CONTINUED", "END", "THE END", "OMITTED", "BLACK", "ANGLE",
    "CLOSE", "CLOSEUP", "CLOSE UP", "WIDE ANGLE", "TWO SHOT",
    "P.O.V.", "POV", "CAST", "CREDITS", "MUSIC IN", "MUSIC OUT",
    "TAG", "TEASER", "MAIN TITLE",
}
RE_PARENTHETICAL = re.compile(r"^\s*\((?P<text>[^)]+)\)\s*$")
RE_BLANK = re.compile(r"^\s*$")

RE_TITLE = re.compile(r'"([^"]+)"')
RE_STARDATE = re.compile(r"stardate\s+([0-9]+\.?[0-9]*)", re.IGNORECASE)
RE_WRITTEN_BY = re.compile(r"(?:Written by|by)\s*\n+\s*([^\n#]+)", re.IGNORECASE)
RE_PROD = re.compile(r"#?(\d{5})-(\d{3})")  # e.g. 40277-747

# Known ships / locations seeds (very small Layer-1 seed list)
KNOWN_SHIPS = {
    "Enterprise": ["U.S.S. Enterprise", "USS Enterprise", "Enterprise"],
    "Stargazer": ["U.S.S. Stargazer", "Stargazer"],
}

# ---- Data --------------------------------------------------------------------


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
    series: str = "TNG"
    title: str | None = None
    writer: str | None = None
    director: str | None = None
    stardate: str | None = None
    production_code: str | None = None
    characters: list[dict] = field(default_factory=list)
    scenes: list[Scene] = field(default_factory=list)
    lines: list[Line] = field(default_factory=list)
    ships: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---- Helpers -----------------------------------------------------------------


def _clean_name(name: str) -> str:
    name = name.strip().rstrip(":").strip()
    # Drop trailing CONT'D / V.O. / O.S. fragments
    name = re.sub(r"\s*\(?(CONT'D|CONTD|V\.O\.|O\.S\.|OS|VO)\)?$", "", name).strip()
    return name


def _is_cue_name(name: str) -> bool:
    if not name or len(name) < 2:
        return False
    if name in NON_CUE:
        return False
    if any(name.startswith(p) for p in ("INT.", "EXT.", "FADE", "CUT", "DISSOLVE")):
        return False
    # Must have at least one letter; reject pure numbers
    if not re.search(r"[A-Z]", name):
        return False
    # Reject overly long all-caps "lines" (probably action)
    if len(name) > 30:
        return False
    return True


def _split_location(heading: str) -> tuple[str | None, str | None]:
    m = re.match(r"\s*(INT\.|EXT\.|INT\./EXT\.|EXT\./INT\.)\s*(.+)", heading, re.IGNORECASE)
    if not m:
        return None, heading.strip()
    int_ext = m.group(1).upper().rstrip(".")
    rest = m.group(2).strip()
    # location is up to first " - "
    loc = rest.split(" - ")[0].strip()
    return int_ext, loc or None


def _extract_header_meta(text: str, ps: ParsedScript) -> None:
    head = text[:3000]
    if m := RE_TITLE.search(head):
        ps.title = m.group(1).strip()
    if m := RE_PROD.search(head):
        ps.production_code = f"{m.group(1)}-{m.group(2)}"
    # writer
    m = re.search(
        r"(?:Written by|Teleplay by|Story by|by)\s*\n+([^\n]+(?:\n\s+(?:and|&)\s+[^\n]+)*)",
        head,
    )
    if m:
        w = re.sub(r"\s+", " ", m.group(1)).strip(" .")
        # Filter out junk that captured "FINAL DRAFT" etc.
        if not any(k in w.upper() for k in ("DRAFT", "COPYRIGHT", "PUBLICATION")):
            ps.writer = w
    m = re.search(r"Directed by\s*\n+\s*([^\n]+)", head, re.IGNORECASE)
    if m:
        ps.director = re.sub(r"\s+", " ", m.group(1)).strip(" .")
    # Stardate often in first dialogue, scan more text
    if m := RE_STARDATE.search(text[:20000]):
        ps.stardate = m.group(1)


def _extract_cast_table(text: str, ps: ParsedScript) -> set[str]:
    """Find a CAST block and pull names."""
    cast_names: set[str] = set()
    m = re.search(r"\n\s*CAST\s*\n(.+?)(?:\n\s*SETS\s*\n|\n\s*\d+\s+(?:INT|EXT)\.|\nFADE IN)",
                  text, re.IGNORECASE | re.DOTALL)
    if not m:
        ps.warnings.append("No CAST block detected; relying on cue extraction")
        return cast_names
    block = m.group(1)
    for raw in block.splitlines():
        # tokens are space-separated columns; whitelist all-caps name-ish tokens
        for tok in re.split(r"\s{2,}", raw.strip()):
            tok = tok.strip()
            if not tok:
                continue
            if _is_cue_name(tok) and tok not in NON_CUE:
                cast_names.add(_clean_name(tok))
    return cast_names


# ---- Main parse --------------------------------------------------------------


def parse_script(script_id: str, text: str) -> ParsedScript:
    ps = ParsedScript(id=script_id)
    _extract_header_meta(text, ps)
    cast_seed = _extract_cast_table(text, ps)

    lines = text.splitlines()
    cur_scene: Scene | None = None
    cur_act: str | None = None
    scene_counter = 0
    line_counter = 0

    i = 0
    seen_chars: dict[str, dict] = {}
    for name in cast_seed:
        seen_chars[name] = {"canonical_name": name, "first_line": None, "line_count": 0}

    ships_seen: set[str] = set()
    locations_seen: set[str] = set()

    while i < len(lines):
        ln = lines[i]
        stripped = ln.strip()

        if RE_BLANK.match(ln):
            i += 1
            continue

        # ACT / TEASER marker
        if RE_ACT.match(stripped):
            cur_act = stripped
            i += 1
            continue

        # CONTINUED continuation (skip)
        if RE_CONTINUED.match(ln):
            i += 1
            continue

        # Scene heading
        m = RE_SCENE_HEADER.match(ln)
        if m and ("INT." in m.group("head").upper() or "EXT." in m.group("head").upper()):
            scene_counter += 1
            int_ext, loc = _split_location(m.group("head"))
            cur_scene = Scene(
                scene_idx=scene_counter,
                number=m.group("num"),
                heading=m.group("head").strip(),
                int_ext=int_ext,
                location=loc,
                act=cur_act,
            )
            ps.scenes.append(cur_scene)
            if loc:
                locations_seen.add(loc)
            i += 1
            continue

        # Character cue
        cm = RE_CUE.match(ln)
        if cm:
            name = _clean_name(cm.group("name"))
            if _is_cue_name(name):
                paren = cm.group("paren")
                # Collect following parenthetical(s) + dialogue until blank line / next cue / scene
                j = i + 1
                dialogue_parts: list[str] = []
                extra_paren: list[str] = []
                while j < len(lines):
                    nxt = lines[j]
                    if RE_BLANK.match(nxt):
                        break
                    if RE_CUE.match(nxt):
                        break
                    if RE_SCENE_HEADER.match(nxt) and ("INT." in nxt.upper() or "EXT." in nxt.upper()):
                        break
                    pm = RE_PARENTHETICAL.match(nxt)
                    if pm:
                        extra_paren.append(pm.group("text").strip())
                    else:
                        # dialogue line (strip leading whitespace, but preserve text)
                        dialogue_parts.append(nxt.strip())
                    j += 1
                text_joined = " ".join(p for p in dialogue_parts if p).strip()
                if text_joined:
                    line_counter += 1
                    full_paren = "; ".join([p for p in [paren, *extra_paren] if p]) or None
                    li = Line(
                        line_num=line_counter,
                        speaker=name,
                        text=text_joined,
                        parenthetical=full_paren,
                        scene_idx=cur_scene.scene_idx if cur_scene else None,
                    )
                    ps.lines.append(li)
                    ch = seen_chars.setdefault(
                        name, {"canonical_name": name, "first_line": line_counter, "line_count": 0}
                    )
                    if ch["first_line"] is None:
                        ch["first_line"] = line_counter
                    ch["line_count"] += 1
                i = j
                continue

        # Action line — scan for ships/locations of interest
        upper = stripped
        for canon, aliases in KNOWN_SHIPS.items():
            if any(a in upper for a in aliases):
                ships_seen.add(canon)
                break

        i += 1

    # Filter characters: keep only those with >=1 line OR in cast seed
    ps.characters = sorted(seen_chars.values(), key=lambda c: -c["line_count"])
    ps.ships = sorted(ships_seen)
    ps.locations = sorted(locations_seen)

    if not ps.lines:
        ps.warnings.append("No dialogue lines extracted")
    if not ps.scenes:
        ps.warnings.append("No scenes extracted")
    if not ps.title:
        ps.warnings.append("Title not detected")
    return ps


def to_dict(ps: ParsedScript) -> dict:
    d = asdict(ps)
    return d


def parse_file(path: Path) -> ParsedScript:
    text = path.read_text(encoding="utf-8", errors="replace")
    return parse_script(path.stem, text)


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    root = Path(__file__).resolve().parents[1]
    raw_dir = root / "data" / "raw"
    out_dir = root / "data" / "parsed"
    out_dir.mkdir(parents=True, exist_ok=True)

    files: Iterable[Path]
    if argv:
        files = [Path(a) for a in argv]
    else:
        files = sorted(raw_dir.glob("*.txt"))

    for f in files:
        if not f.exists():
            log.error("Missing: %s", f)
            continue
        ps = parse_file(f)
        out = out_dir / f"{f.stem}.json"
        out.write_text(json.dumps(to_dict(ps), indent=2, ensure_ascii=False))
        print(
            f"[parse] {f.stem}: title={ps.title!r:40s} "
            f"scenes={len(ps.scenes):3d} lines={len(ps.lines):4d} "
            f"chars={len(ps.characters):3d} warn={len(ps.warnings)}"
        )
        for w in ps.warnings:
            log.warning("  %s: %s", f.stem, w)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
