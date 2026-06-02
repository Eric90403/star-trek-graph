#!/usr/bin/env python3
"""Sanity tests for DS9 ingest — anchored on episode 402 (Emissary, pilot)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
JSON_PATH = ROOT / "data" / "parsed" / "ds9_402.json"


@pytest.fixture(scope="module")
def emissary() -> dict:
    if not JSON_PATH.exists():
        pytest.skip(f"{JSON_PATH} not present — run scripts/ingest_ds9.py --parse-only first")
    return json.loads(JSON_PATH.read_text())


def test_title_contains_emissary(emissary):
    title = (emissary.get("title") or "").lower()
    assert "emissary" in title, f"Expected 'Emissary' in title, got {emissary.get('title')!r}"


def test_series_tagged_ds9(emissary):
    assert emissary.get("series") == "DS9"


def test_main_cast_present(emissary):
    names = {c["canonical_name"].upper() for c in emissary.get("characters", [])}
    for cue in ("SISKO", "KIRA", "ODO", "BASHIR"):
        assert cue in names, f"{cue} missing from parsed cast: {sorted(names)[:25]}"


def test_at_least_200_lines(emissary):
    n = len(emissary.get("lines", []))
    assert n >= 200, f"Expected >= 200 dialogue lines, got {n}"
