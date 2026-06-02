"""Basic parser sanity checks on script 102 (Encounter at Farpoint)."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from parser import parse_file  # noqa: E402

RAW = ROOT / "data" / "raw" / "102.txt"


def test_102_parses():
    assert RAW.exists(), f"Expected raw script at {RAW}; run scripts/fetch_scripts.py first"
    ps = parse_file(RAW)
    # Title check
    assert ps.title and "Farpoint" in ps.title, f"title={ps.title!r}"
    # Major TNG characters should be present
    names = {c["canonical_name"] for c in ps.characters}
    for expected in ("PICARD", "DATA", "RIKER", "TROI"):
        assert expected in names, f"missing character {expected} in {sorted(names)[:30]}"
    # Reasonable line count for a feature-length pilot
    assert len(ps.lines) > 200, f"only {len(ps.lines)} dialogue lines parsed"
    # Scenes
    assert len(ps.scenes) > 30, f"only {len(ps.scenes)} scenes parsed"
    # Enterprise should be detected as a ship
    assert "Enterprise" in ps.ships


def test_picard_speaks():
    ps = parse_file(RAW)
    picard_lines = [l for l in ps.lines if l["speaker"] == "PICARD"] if isinstance(ps.lines[0], dict) else [l for l in ps.lines if l.speaker == "PICARD"]
    assert len(picard_lines) > 40, f"Picard only has {len(picard_lines)} lines"
