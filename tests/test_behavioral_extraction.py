"""Light smoke tests for behavioral extractor (no LLM calls)."""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from neo4j import GraphDatabase
from config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
from behavioral_extractor import (
    get_top_characters,
    sample_lines_for_character,
)


@pytest.fixture(scope="module")
def driver():
    d = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        # skip if neo4j unreachable
        with d.session() as s:
            s.run("RETURN 1").single()
    except Exception as e:
        pytest.skip(f"Neo4j unavailable: {e}")
    yield d
    d.close()


def test_get_top_characters_returns_20_with_picard_first(driver):
    tops = get_top_characters(driver, limit=20)
    assert len(tops) == 20
    assert tops[0]["canonical_name"] == "PICARD"
    for t in tops:
        assert "canonical_name" in t
        assert "total_lines" in t and t["total_lines"] > 0
        assert isinstance(t["series_breakdown"], dict)


def test_sample_lines_shape(driver):
    lines = sample_lines_for_character(driver, "PICARD", sample_size=50)
    assert 30 <= len(lines) <= 60  # allow some dedup
    sample = lines[0]
    for k in ("text", "parenthetical", "episode_title", "stardate"):
        assert k in sample
    assert isinstance(sample["text"], str) and sample["text"]


def test_sample_lines_unknown_character(driver):
    lines = sample_lines_for_character(driver, "NOT_A_REAL_CHARACTER_XYZ", sample_size=50)
    assert lines == []
