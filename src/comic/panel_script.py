"""src/comic/panel_script.py — PanelScript data model.

Defines the explicit script structure that drives the reading-order
balloon placer. The script is the AUTHORITATIVE source of reading
order — the placer never infers it from pixel positions.

Design references:
  - data/COMIC_PIPELINE_DESIGN.md §2 (data model spec)
  - data/COMIC_BEST_PRACTICES.md §2 (reading order as script order)

Usage:
    from comic.panel_script import PanelScript, ScriptLine, LineType

    script = PanelScript(
        scene="Bridge - Night Watch",
        panel_id="page1_panel2",
        lines=[
            ScriptLine(order=1, speaker="PICARD",
                       text="Two centuries. A long time to wait for rescue."),
            ScriptLine(order=2, speaker="WORF",
                       text="Or a long time for a trap to remain set.",
                       line_type=LineType.RADIO, off_panel=True,
                       listener="PICARD"),
        ],
    )

The placer consumes this and produces a list of BalloonPlacement objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Optional, Dict, Any


class LineType(Enum):
    """How a script line should be rendered.

    Maps to BalloonType in balloons.py (with the same names) plus caption
    variants. The renderer dispatches on this; the placer uses it to skip
    certain scoring terms (e.g. speaker proximity is irrelevant for RADIO).
    """
    NORMAL  = "normal"   # In-person speech: rounded rect, smooth tail
    RADIO   = "radio"    # Combadge/viewscreen/intercom: double outline, no tail
    SHOUT   = "shout"    # Loud/burst: jagged outline
    WHISPER = "whisper"  # Quiet: dashed outline
    CAPTION = "caption"  # Narration box (yellow default)
    LOG     = "log"      # Captain's Log (cyan, italic, IDW Trek convention)


@dataclass
class ScriptLine:
    """One line of dialogue/caption in a panel.

    Attributes:
        order: Reading-order index. 1 = first balloon the reader sees.
            Must be unique within a panel. The placer iterates lines
            in this order (NOT in list insertion order, in case scripts
            are loaded from a different source order).
        speaker: Canonical character name (uppercase, e.g. "PICARD").
            For CAPTION/LOG lines, this is typically the narrator ("NARRATOR",
            "PICARD" for log entries, or empty string for location captions).
        text: The dialogue (without any inline tag — the renderer adds
            the "Speaker via Comms:" prefix for RADIO lines).
        line_type: How to render. Defaults to NORMAL.
        off_panel: True if the speaker is not visible in this panel
            (e.g. WORF on a different ship, comm-only). Affects tail
            rendering (NORMAL: no tail; RADIO: always no tail) but NOT
            placement (the placer uses reading order, not an anchor).
        listener: For RADIO lines, who is receiving the call. Used for
            context/logging only; the placer does NOT use this to find
            an anchor (BBP §5 — no anchor for radio balloons).
    """
    order: int
    speaker: str
    text: str
    line_type: LineType = LineType.NORMAL
    off_panel: bool = False
    listener: Optional[str] = None

    def __post_init__(self):
        if self.order < 1:
            raise ValueError(f"ScriptLine.order must be >= 1, got {self.order}")
        if not self.text.strip():
            raise ValueError(f"ScriptLine.text cannot be empty (order={self.order})")
        # Speaker can be empty for pure narration captions, but flag for normal lines
        if self.line_type == LineType.NORMAL and not self.speaker.strip():
            raise ValueError(
                f"NORMAL ScriptLine requires a speaker (order={self.order}). "
                f"Use LineType.CAPTION for narration without a speaker."
            )


@dataclass
class PanelScript:
    """A complete script for one panel.

    Attributes:
        scene: Human-readable scene description
            (e.g. "Bridge - Night Watch"). Used in prompts and logs.
        panel_id: Traceability identifier (e.g. "page1_panel2"). Used in
            log output and as a filename prefix for generated art.
        lines: The script lines, in any order. The placer sorts by
            `order` field, so this list does not need to be pre-sorted.
            Must contain at least one line.
        speaker_positions: Optional override mapping speaker name to
            canvas position ("left" / "right" / "center"). The placer
            uses this for two-shot panels to bias the first balloon
            toward the left character (BBP §2, Rule 3). If not provided,
            the placer infers from face bounding boxes.

    Invariants (enforced in __post_init__):
        - len(lines) >= 1
        - All `order` values are unique within this panel
    """
    scene: str
    panel_id: str
    lines: List[ScriptLine]
    speaker_positions: Optional[Dict[str, str]] = None

    def __post_init__(self):
        if not self.lines:
            raise ValueError(f"PanelScript '{self.panel_id}' must have at least one line")
        orders = [line.order for line in self.lines]
        if len(orders) != len(set(orders)):
            from collections import Counter
            dupes = [o for o, c in Counter(orders).items() if c > 1]
            raise ValueError(
                f"PanelScript '{self.panel_id}' has duplicate order values: {dupes}. "
                f"Each ScriptLine must have a unique order."
            )
        # Validate speaker_positions if provided
        if self.speaker_positions is not None:
            valid_positions = {"left", "right", "center", "top", "bottom"}
            for speaker, pos in self.speaker_positions.items():
                if pos not in valid_positions:
                    raise ValueError(
                        f"speaker_positions['{speaker}'] = '{pos}' invalid. "
                        f"Must be one of: {valid_positions}"
                    )

    def sorted_lines(self) -> List[ScriptLine]:
        """Return lines sorted by reading order. This is the canonical
        iteration order for the placer."""
        return sorted(self.lines, key=lambda l: l.order)

    def radio_lines(self) -> List[ScriptLine]:
        """Return only RADIO lines (combadge/viewscreen/intercom)."""
        return [l for l in self.sorted_lines() if l.line_type == LineType.RADIO]

    def normal_lines(self) -> List[ScriptLine]:
        """Return only NORMAL lines (in-person speech)."""
        return [l for l in self.sorted_lines() if l.line_type == LineType.NORMAL]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-compatible dict. Useful for caching
        scripts to disk, debug logging, and reproducibility."""
        return {
            "scene": self.scene,
            "panel_id": self.panel_id,
            "speaker_positions": self.speaker_positions,
            "lines": [
                {
                    "order": l.order,
                    "speaker": l.speaker,
                    "text": l.text,
                    "line_type": l.line_type.value,
                    "off_panel": l.off_panel,
                    "listener": l.listener,
                }
                for l in self.lines
            ],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PanelScript":
        """Construct from a dict (inverse of to_dict). Useful for
        loading scripts from JSON."""
        return cls(
            scene=d["scene"],
            panel_id=d["panel_id"],
            lines=[
                ScriptLine(
                    order=ld["order"],
                    speaker=ld["speaker"],
                    text=ld["text"],
                    line_type=LineType(ld.get("line_type", "normal")),
                    off_panel=ld.get("off_panel", False),
                    listener=ld.get("listener"),
                )
                for ld in d["lines"]
            ],
            speaker_positions=d.get("speaker_positions"),
        )


__all__ = ["LineType", "ScriptLine", "PanelScript"]
