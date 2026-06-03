"""Unit tests for src/comic/panel_script.py.

Covers construction, validation, and round-trip serialization.
Pure data structure — no API calls, runs in <1s.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest
from comic.panel_script import LineType, PanelScript, ScriptLine


# ── Construction (happy path) ────────────────────────────────────────────────

def test_basic_construction():
    script = PanelScript(
        scene="Bridge - Night",
        panel_id="p1_p2",
        lines=[
            ScriptLine(order=1, speaker="PICARD", text="Make it so."),
            ScriptLine(order=2, speaker="WORF", text="Aye, Captain."),
        ],
    )
    assert script.scene == "Bridge - Night"
    assert script.panel_id == "p1_p2"
    assert len(script.lines) == 2

def test_construction_with_radio_and_log():
    script = PanelScript(
        scene="Bridge",
        panel_id="p1_p3",
        lines=[
            ScriptLine(order=1, speaker="PICARD", text="Captain's log, stardate 47988.0.",
                       line_type=LineType.LOG),
            ScriptLine(order=2, speaker="WORF", text="Captain, we are being hailed.",
                       line_type=LineType.RADIO, off_panel=True, listener="PICARD"),
        ],
    )
    assert len(script.radio_lines()) == 1
    assert len(script.normal_lines()) == 0
    assert script.radio_lines()[0].speaker == "WORF"

def test_construction_with_speaker_positions():
    script = PanelScript(
        scene="Two-shot",
        panel_id="p1_p5",
        lines=[
            ScriptLine(order=1, speaker="PICARD", text="Engage."),
            ScriptLine(order=2, speaker="RIKER", text="Aye, sir."),
        ],
        speaker_positions={"PICARD": "left", "RIKER": "right"},
    )
    assert script.speaker_positions == {"PICARD": "left", "RIKER": "right"}


# ── Validation (sad path) ───────────────────────────────────────────────────

def test_empty_lines_allowed_for_art_only_panels():
    """Empty `lines` is allowed for art-only / establishing-shot panels.
    The placer skips placement entirely for these (the renderer just
    copies the art straight to FINAL)."""
    script = PanelScript(scene="Establishing shot", panel_id="p1", lines=[])
    assert script.lines == []
    assert script.sorted_lines() == []
    assert script.radio_lines() == []
    assert script.normal_lines() == []

def test_duplicate_order_rejected():
    with pytest.raises(ValueError, match="duplicate order"):
        PanelScript(
            scene="X",
            panel_id="y",
            lines=[
                ScriptLine(order=1, speaker="A", text="First."),
                ScriptLine(order=1, speaker="B", text="Also first (bad)."),
            ],
        )

def test_normal_line_without_speaker_rejected():
    with pytest.raises(ValueError, match="NORMAL ScriptLine requires a speaker"):
        PanelScript(
            scene="X",
            panel_id="y",
            lines=[ScriptLine(order=1, speaker="", text="Hello.")],
        )

def test_caption_line_can_have_no_speaker():
    # This should NOT raise — pure narration captions have no speaker
    script = PanelScript(
        scene="X",
        panel_id="y",
        lines=[ScriptLine(order=1, speaker="", text="A long time ago...",
                          line_type=LineType.CAPTION)],
    )
    assert script.lines[0].speaker == ""

def test_invalid_speaker_position_rejected():
    with pytest.raises(ValueError, match="invalid"):
        PanelScript(
            scene="X",
            panel_id="y",
            lines=[ScriptLine(order=1, speaker="A", text="Hi.")],
            speaker_positions={"A": "diagonal"},  # not a valid position
        )

def test_empty_text_rejected():
    with pytest.raises(ValueError, match="cannot be empty"):
        ScriptLine(order=1, speaker="PICARD", text="   ")

def test_order_zero_rejected():
    with pytest.raises(ValueError, match="order must be >= 1"):
        ScriptLine(order=0, speaker="PICARD", text="Engage.")


# ── sorted_lines / filters ───────────────────────────────────────────────────

def test_sorted_lines_orders_by_field_not_list_position():
    # Insert lines out of order; sorted_lines() must return them in
    # reading order regardless of insertion order
    script = PanelScript(
        scene="X",
        panel_id="y",
        lines=[
            ScriptLine(order=3, speaker="C", text="Third."),
            ScriptLine(order=1, speaker="A", text="First."),
            ScriptLine(order=2, speaker="B", text="Second."),
        ],
    )
    ordered = script.sorted_lines()
    assert [l.speaker for l in ordered] == ["A", "B", "C"]
    assert [l.order for l in ordered] == [1, 2, 3]

def test_radio_lines_excludes_normal():
    script = PanelScript(
        scene="X",
        panel_id="y",
        lines=[
            ScriptLine(order=1, speaker="PICARD", text="In person."),
            ScriptLine(order=2, speaker="WORF", text="On comms.",
                       line_type=LineType.RADIO, off_panel=True),
        ],
    )
    assert len(script.radio_lines()) == 1
    assert script.radio_lines()[0].line_type == LineType.RADIO
    assert len(script.normal_lines()) == 1


# ── to_dict / from_dict round trip ──────────────────────────────────────────

def test_to_dict_basic():
    script = PanelScript(
        scene="Bridge",
        panel_id="p1_p2",
        lines=[ScriptLine(order=1, speaker="PICARD", text="Engage.")],
    )
    d = script.to_dict()
    assert d["scene"] == "Bridge"
    assert d["panel_id"] == "p1_p2"
    assert d["lines"][0]["speaker"] == "PICARD"
    assert d["lines"][0]["line_type"] == "normal"

def test_from_dict_basic():
    d = {
        "scene": "Bridge",
        "panel_id": "p1_p2",
        "lines": [
            {"order": 1, "speaker": "PICARD", "text": "Engage.",
             "line_type": "normal", "off_panel": False, "listener": None},
        ],
    }
    script = PanelScript.from_dict(d)
    assert script.scene == "Bridge"
    assert script.lines[0].speaker == "PICARD"

def test_round_trip_preserves_all_fields():
    original = PanelScript(
        scene="Bridge",
        panel_id="p1_p5",
        lines=[
            ScriptLine(order=1, speaker="PICARD", text="Engage."),
            ScriptLine(order=2, speaker="WORF", text="Hailing frequency open.",
                       line_type=LineType.RADIO, off_panel=True, listener="PICARD"),
        ],
        speaker_positions={"PICARD": "left"},
    )
    d = original.to_dict()
    restored = PanelScript.from_dict(d)
    assert restored.scene == original.scene
    assert restored.panel_id == original.panel_id
    assert restored.speaker_positions == original.speaker_positions
    assert len(restored.lines) == len(original.lines)
    assert restored.sorted_lines()[1].line_type == LineType.RADIO
    assert restored.sorted_lines()[1].off_panel is True
    assert restored.sorted_lines()[1].listener == "PICARD"
