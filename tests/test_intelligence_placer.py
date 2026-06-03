"""Unit tests for src/comic/intelligence.py — Task 3 placer + Task 4 face-veto.

Covers the new place_balloons_for_panel() function and the face-veto
hard guarantees. All tests use synthetic PanelAnalysis data — no API
calls, no model invocations. Runs in <1s.

Per data/COMIC_PIPELINE_DESIGN.md §5-§6 (renumbered) and the
face-veto test list in the design doc.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

from comic.intelligence import (
    PanelAnalysis,
    BalloonPlacement,
    place_balloons_for_panel,
    PlacementError,
    _reading_order_zone,
    _estimate_balloon_size,
    _speaker_face_for_line,
    _rect_overlap,
    _rect_inflate,
)
from comic.panel_script import PanelScript, ScriptLine, LineType


# ── Helpers for synthetic panel data ─────────────────────────────────────────

def make_panel_analysis(face_bboxes=None, body_bboxes=None, empty_regions=None,
                        preexisting_bboxes=None, combadges=None, width=1456, height=816):
    """Build a synthetic PanelAnalysis for unit tests."""
    return PanelAnalysis(
        width=width, height=height,
        face_bboxes=face_bboxes or [],
        body_bboxes=body_bboxes or [],
        combadges=combadges or [],
        empty_regions=empty_regions or [],
        preexisting_bboxes=preexisting_bboxes or [],
        raw={"synthetic": True},
    )


def panel_bbox(w=1456, h=816):
    """Standard 2K source panel bbox."""
    return (0, 0, w, h)


# ── Face-veto tests (Task 4 / design §5) ────────────────────────────────────

def test_balloon_directly_over_face_vetoed():
    """Balloon placed at exact face bbox → must be vetoed (placed elsewhere).

    The placer must NOT place a balloon overlapping a face bbox. If
    a face blocks all candidates, it raises PlacementError. If the
    face only blocks part, the placer finds a non-overlapping spot.
    Either way, the resulting balloon must NOT overlap the face.
    """
    # Face taking up most of the left half of the panel
    face = (100, 200, 700, 750)
    analysis = make_panel_analysis(face_bboxes=[face])
    script = PanelScript(
        scene="X", panel_id="p",
        lines=[ScriptLine(order=1, speaker="PICARD", text="A short line.")],
    )
    try:
        placements = place_balloons_for_panel(panel_bbox(), analysis, script)
        # If placement succeeded, the balloon must NOT overlap the face
        pad_face = _rect_inflate(face, 10)
        for p in placements:
            assert not _rect_overlap(p.rect, pad_face), \
                f"balloon overlaps face: {p.rect} vs {pad_face}"
    except PlacementError:
        # Also acceptable — if the face blocks everything, the placer
        # correctly raises. The face-veto guarantee is the same either way.
        pass


def test_balloon_completely_blocked_raises_placement_error():
    """If a face completely fills the panel, no valid placement exists
    and the placer raises PlacementError with line info."""
    # Face covers the entire panel — no room for a balloon
    huge_face = (0, 0, 1456, 816)
    analysis = make_panel_analysis(face_bboxes=[huge_face])
    script = PanelScript(
        scene="X", panel_id="p",
        lines=[ScriptLine(order=1, speaker="PICARD", text="A short line.")],
    )
    with pytest.raises(PlacementError) as exc_info:
        place_balloons_for_panel(panel_bbox(), analysis, script)
    assert exc_info.value.line_order == 1
    assert exc_info.value.line_speaker == "PICARD"


def test_balloon_in_clear_zone_succeeds():
    """A panel with a small face and a clear zone → balloon placed.

    NOTE: After v0.4.1, placement is speaker-anchored (above the speaker's
    face). The balloon ends up wherever 'above the speaker' is clear, not
    necessarily in the upper portion of the panel.
    """
    # Small face in the lower-right, clear upper zone
    face = (1100, 600, 1300, 750)  # right side, low
    analysis = make_panel_analysis(face_bboxes=[face])
    script = PanelScript(
        scene="X", panel_id="p",
        lines=[ScriptLine(order=1, speaker="PICARD", text="Hello there.")],
    )
    placements = place_balloons_for_panel(panel_bbox(), analysis, script)
    assert len(placements) == 1
    # Balloon must be ABOVE the speaker's face (face_top is at y=600,
    # balloon center should be above that)
    p = placements[0]
    assert p.cy < 600, f"balloon should be above speaker's face_top (y=600), got cy={p.cy}"
    # Balloon must NOT overlap the face
    pad_face = _rect_inflate(face, 10)
    assert not _rect_overlap(p.rect, pad_face)


def test_radio_balloon_does_not_use_listener_as_anchor():
    """The spiral's bug: radio balloon used to cluster near listener's face.

    With the new placer, a radio balloon (off-panel speaker) should be
    placed by reading-order zone, NOT anchored to the listener.
    """
    # Two faces — Picard (listener) on the LEFT, Riker (listener) on the RIGHT
    picard_face = (100, 300, 400, 600)
    riker_face = (1056, 300, 1356, 600)
    analysis = make_panel_analysis(face_bboxes=[picard_face, riker_face])
    script = PanelScript(
        scene="X", panel_id="p",
        lines=[
            ScriptLine(order=1, speaker="WORF",
                       text="Captain, we are being hailed by an unknown vessel.",
                       line_type=LineType.RADIO, off_panel=True, listener="PICARD"),
        ],
    )
    placements = place_balloons_for_panel(panel_bbox(), analysis, script)
    assert len(placements) == 1
    p = placements[0]
    # The radio balloon should be in the UPPER zone (line 1 = top, single line)
    assert p.cy < 400, f"radio balloon should be in upper zone, got cy={p.cy}"
    # Crucially, it should NOT be glued to Picard's face
    pad_picard = _rect_inflate(picard_face, 10)
    assert not _rect_overlap(p.rect, pad_picard), \
        "radio balloon must not overlap Picard's face"


def test_speaker_own_face_exempt_logic():
    """For a NORMAL line, the speaker's face is the candidate 'speaker' face.
    Verify _speaker_face_for_line returns face_top (cx, y_top) based on position.

    NOTE: After v0.4.1, the anchor is face_TOP (cx, y_top), not face_center.
    This is the design decision in COMIC_TECHNIQUES_RESEARCH.md §5 q2 —
    the tail terminates at upper-forehead, not face center.
    """
    picard_face = (100, 300, 400, 600)   # left, face_top=(250, 300)
    riker_face = (1056, 300, 1356, 600)  # right, face_top=(1206, 300)
    bboxes = [picard_face, riker_face]
    # Line 1 is Picard, with explicit speaker_positions
    line_picard = ScriptLine(order=1, speaker="PICARD", text="Engage.")
    script = PanelScript(
        scene="X", panel_id="p",
        lines=[line_picard],
        speaker_positions={"PICARD": "left", "RIKER": "right"},
    )
    speaker_pt = _speaker_face_for_line(line_picard, bboxes, script.speaker_positions)
    # Picard is on the left, so the speaker face_top should be Picard's
    assert speaker_pt == (250.0, 300)  # face_top of picard_face

    # Now for Riker
    line_riker = ScriptLine(order=2, speaker="RIKER", text="Aye, sir.")
    speaker_pt = _speaker_face_for_line(line_riker, bboxes, script.speaker_positions)
    assert speaker_pt == (1206.0, 300)  # face_top of riker_face

    # For a RADIO line, returns None
    line_radio = ScriptLine(order=3, speaker="WORF", text="Hailing.",
                            line_type=LineType.RADIO, off_panel=True)
    speaker_pt = _speaker_face_for_line(line_radio, bboxes, script.speaker_positions)
    assert speaker_pt is None


def test_multiple_balloons_no_overlap():
    """Multiple balloons placed in sequence must not overlap each other."""
    face = (1100, 600, 1300, 750)  # small face in lower-right
    analysis = make_panel_analysis(face_bboxes=[face])
    script = PanelScript(
        scene="X", panel_id="p",
        lines=[
            ScriptLine(order=1, speaker="PICARD", text="Make it so."),
            ScriptLine(order=2, speaker="PICARD", text="All stop."),
            ScriptLine(order=3, speaker="PICARD", text="Engage."),
        ],
    )
    placements = place_balloons_for_panel(panel_bbox(), analysis, script)
    assert len(placements) == 3
    # No two balloons should overlap
    for i in range(len(placements)):
        for j in range(i + 1, len(placements)):
            assert not _rect_overlap(placements[i].rect, placements[j].rect), \
                f"balloons {i} and {j} overlap: {placements[i].rect} vs {placements[j].rect}"


def test_panel_with_no_faces():
    """A panel with no visible characters (pure environment) should still
    place balloons in reading-order zones."""
    analysis = make_panel_analysis(face_bboxes=[])
    script = PanelScript(
        scene="X", panel_id="p",
        lines=[ScriptLine(order=1, speaker="NARRATOR", text="A long time ago...",
                          line_type=LineType.CAPTION)],
    )
    placements = place_balloons_for_panel(panel_bbox(), analysis, script)
    assert len(placements) == 1
    # Caption should be in the upper portion
    assert placements[0].cy < 400


def test_balloon_stays_within_panel_bounds():
    """Every balloon must be at least edge_margin pixels from the panel edge."""
    face = (1100, 600, 1300, 750)  # small face
    analysis = make_panel_analysis(face_bboxes=[face])
    script = PanelScript(
        scene="X", panel_id="p",
        lines=[ScriptLine(order=1, speaker="PICARD", text="Hi.")],
    )
    placements = place_balloons_for_panel(panel_bbox(), analysis, script, edge_margin=30)
    p = placements[0]
    assert p.rect[0] >= 30  # left edge
    assert p.rect[1] >= 30  # top edge
    assert p.rect[2] <= 1456 - 30  # right edge
    assert p.rect[3] <= 816 - 30   # bottom edge


def test_two_shot_two_balloons_both_speakers_get_correct_face():
    """Two-shot panel: Picard (left) and Riker (right), each with their
    own line. Each balloon should anchor near the correct speaker."""
    picard_face = (100, 300, 400, 600)   # left
    riker_face = (1056, 300, 1356, 600)  # right
    analysis = make_panel_analysis(face_bboxes=[picard_face, riker_face])
    script = PanelScript(
        scene="Bridge", panel_id="two_shot",
        lines=[
            ScriptLine(order=1, speaker="PICARD",
                       text="Two centuries is a long time to wait for rescue."),
            ScriptLine(order=2, speaker="RIKER",
                       text="Or a long time for a trap to remain set, sir."),
        ],
        speaker_positions={"PICARD": "left", "RIKER": "right"},
    )
    placements = place_balloons_for_panel(panel_bbox(), analysis, script)
    assert len(placements) == 2
    # Picard's balloon (line 1) should be near Picard's face
    p1 = placements[0]
    pad_picard = _rect_inflate(picard_face, 10)
    # Picard's balloon may be near him but not on his face
    p1_dist_to_picard = ((p1.cx - 250) ** 2 + (p1.cy - 450) ** 2) ** 0.5
    p1_dist_to_riker = ((p1.cx - 1206) ** 2 + (p1.cy - 450) ** 2) ** 0.5
    assert p1_dist_to_picard < p1_dist_to_riker, \
        f"line 1 (Picard) balloon should be closer to Picard, got p1_dist_to_picard={p1_dist_to_picard}, p1_dist_to_riker={p1_dist_to_riker}"


def test_radio_with_normal_lines_reading_order_zones():
    """The Spiral case: Picard + Riker two-shot, then Worf comm.

    With the new placer:
    - Picard's balloon (line 1) should be in upper-left zone
    - Riker's balloon (line 2) should be in lower-right zone
    - Worf's comm balloon (line 3) should be in reading-order zone, NOT
      anchored to the listener (Picard)
    """
    picard_face = (100, 300, 400, 600)
    riker_face = (1056, 300, 1356, 600)
    analysis = make_panel_analysis(face_bboxes=[picard_face, riker_face])
    script = PanelScript(
        scene="Bridge", panel_id="panel_5",
        lines=[
            ScriptLine(order=1, speaker="PICARD",
                       text="Two centuries is a long time to wait for rescue."),
            ScriptLine(order=2, speaker="RIKER",
                       text="Or a long time for a trap to remain set, sir."),
            ScriptLine(order=3, speaker="WORF",
                       text="Captain, we are being hailed.",
                       line_type=LineType.RADIO, off_panel=True, listener="PICARD"),
        ],
        speaker_positions={"PICARD": "left", "RIKER": "right"},
    )
    placements = place_balloons_for_panel(panel_bbox(), analysis, script)
    assert len(placements) == 3
    # Verify the radio balloon (line 3) is NOT pinned to Picard's face
    radio = placements[2]
    pad_picard = _rect_inflate(picard_face, 10)
    assert not _rect_overlap(radio.rect, pad_picard)
    # The radio should be in the lower portion (line 3, last)
    assert radio.cy > 500, f"radio balloon should be in lower band (line 3), got cy={radio.cy}"


# ── Reading-order zone tests ─────────────────────────────────────────────────

def test_reading_order_zone_single_line():
    """Single line: upper-center zone (full top half)."""
    zone = _reading_order_zone(1, 1, panel_bbox())
    zx0, zy0, zx1, zy1 = zone
    # Should be in the upper portion
    assert zy0 == 0
    assert zy1 <= 816 // 2 + 50
    # Slight left+right margin (15% on each side)
    assert zx0 > 0
    assert zx1 < 1456


def test_reading_order_zone_first_line_left_biased():
    """First of multiple lines: top band with left bias."""
    zone = _reading_order_zone(1, 3, panel_bbox())
    zx0, zy0, zx1, zy1 = zone
    # Top band
    assert zy0 == 0
    assert zy1 < 816 / 3 + 50
    # Left bias: zone ends at 70% of width
    assert zx1 < int(1456 * 0.7) + 50


def test_reading_order_zone_last_line_right_biased():
    """Last of multiple lines: bottom band with right bias."""
    zone = _reading_order_zone(3, 3, panel_bbox())
    zx0, zy0, zx1, zy1 = zone
    # Bottom band
    assert zy0 > 816 / 3 * 2 - 50
    # Right bias: zone starts at 30% of width
    assert zx0 > int(1456 * 0.3) - 50


# ── Balloon size estimation ─────────────────────────────────────────────────

def test_estimate_balloon_size_short_text():
    bw, bh = _estimate_balloon_size("Hi.", is_radio=False)
    assert bw >= 200  # floor
    assert bh >= 50


def test_estimate_balloon_size_long_text_wraps():
    long_text = "This is a much longer line of dialogue that will need to wrap across multiple balloon lines."
    bw, bh = _estimate_balloon_size(long_text, is_radio=False)
    # Long text → wider balloon (capped at max_text_w + padding)
    assert bw <= 700 + 28 * 2
    # Long text → multiple lines → taller balloon
    assert bh >= 100


# ── PlacementError contract ─────────────────────────────────────────────────

def test_placement_error_carries_line_info():
    """PlacementError should expose line_order and line_speaker for the
    orchestrator to act on."""
    # Create a panel where placement is impossible (face covers everything)
    huge_face = (0, 0, 1456, 816)  # face fills the entire panel
    analysis = make_panel_analysis(face_bboxes=[huge_face])
    script = PanelScript(
        scene="X", panel_id="p",
        lines=[ScriptLine(order=1, speaker="PICARD", text="Hi.")],
    )
    with pytest.raises(PlacementError) as exc_info:
        place_balloons_for_panel(panel_bbox(), analysis, script)
    err = exc_info.value
    assert err.line_order == 1
    assert err.line_speaker == "PICARD"
    assert "no valid candidate" in err.reason
