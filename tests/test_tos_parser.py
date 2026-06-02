"""Smoke tests for the TOS transcript parser, using episode 42
("The Trouble With Tribbles") as the canonical fixture.

Run from project root:
    .venv/bin/python -m pytest tests/test_tos_parser.py -v
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import tos_parser  # noqa: E402

FIXTURE = ROOT / "data" / "raw" / "tos_42.htm"


@pytest.fixture(scope="module")
def tribbles() -> dict:
    if not FIXTURE.exists():
        pytest.skip(f"fixture missing: {FIXTURE}")
    ps = tos_parser.parse_file(FIXTURE)
    return tos_parser.to_dict(ps)


def test_title_contains_tribbles(tribbles):
    assert tribbles["title"], "title should not be empty"
    assert "tribbles" in tribbles["title"].lower()


def test_id_namespaced(tribbles):
    assert tribbles["id"] == "tos:42"
    assert tribbles["series"] == "TOS"
    assert tribbles["source_type"] == "transcript"


def test_metadata_extracted(tribbles):
    assert tribbles["stardate"] == "4523.3"
    assert "1967" in (tribbles["airdate"] or "")


def test_core_characters_present(tribbles):
    names = {c["canonical_name"] for c in tribbles["characters"]}
    for who in ("KIRK", "SPOCK", "MCCOY"):
        assert who in names, f"{who} missing (got {sorted(names)[:10]}…)"


def test_minimum_line_count(tribbles):
    assert len(tribbles["lines"]) >= 100, \
        f"only {len(tribbles['lines'])} lines parsed; expected >= 100"


def test_captains_log_attributed_to_kirk(tribbles):
    logs = [l for l in tribbles["lines"]
            if (l.get("parenthetical") or "").lower() == "log"]
    assert logs, "no Captain's Log lines detected"
    assert all(l["speaker"] == "KIRK" for l in logs), \
        "Log lines should be attributed to KIRK in TOS"


def test_scene_locations_present(tribbles):
    locs = [s["location"] for s in tribbles["scenes"]]
    # Tribbles famously opens in the briefing room
    assert any("riefing" in (l or "") for l in locs), \
        f"expected a Briefing Room scene; got {locs[:5]}…"
