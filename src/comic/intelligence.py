"""
src/comic/intelligence.py — The intelligence layer.

Two things live here:

  1. analyze_panel(image)
     Calls Claude Sonnet (vision) and returns:
       - face_bboxes:    list of bounding boxes for every visible face
       - body_bboxes:    list of bounding boxes for every visible character body
       - empty_regions:  list of "good empty regions" suitable for word balloons
       - speaker_locs:   dict {character_name: (x, y)} of speaker face centers
                          when characters can be visually identified

  2. find_balloon_position(panel_size, face_bboxes, body_bboxes,
                            empty_regions, balloon_size,
                            speaker_anchor, prior_balloons)
     Returns the best (x, y) for a balloon's CENTER given hard constraints:
       - Balloon rect must NOT intersect any face_bbox  (HARD VETO)
       - Balloon's tail line to speaker must NOT cross any face_bbox  (HARD VETO)
       - Balloon should land inside an empty_region when possible (BONUS)
       - Reading order: top-to-bottom, left-to-right vs. prior balloons (BONUS)

     If no valid position exists, returns None — caller should regenerate
     the panel with explicit composition guidance.
"""

from __future__ import annotations

import base64
import json
import math
import os
import re
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from comic.panel_script import PanelScript, ScriptLine, LineType


# ── Auth ─────────────────────────────────────────────────────────────────────

def _load_openrouter_key() -> str:
    """Resolve OpenRouter API key the same way auth.py does for Anthropic."""
    if k := os.environ.get("OPENROUTER_API_KEY", "").strip():
        return k
    # Fallback: Hermes-style ~/.hermes/.env or ~/.hermes/auth.json
    env_path = Path.home() / ".hermes" / ".env"
    if env_path.exists():
        for ln in env_path.read_text().splitlines():
            if ln.startswith("OPENROUTER_API_KEY="):
                return ln.split("=", 1)[1].strip().strip('"').strip("'")
    auth_path = Path.home() / ".hermes" / "auth.json"
    if auth_path.exists():
        try:
            d = json.loads(auth_path.read_text())
            pool = d.get("credential_pool", {}).get("openrouter", [])
            for entry in pool:
                key = entry.get("access_token") or entry.get("api_key")
                if key:
                    return key
        except (json.JSONDecodeError, KeyError):
            pass
    raise RuntimeError(
        "No OpenRouter API key found.\n"
        "  Set OPENROUTER_API_KEY env var, or add it to ~/.hermes/.env"
    )


# ── Vision analysis (Claude Sonnet via OpenRouter) ────────────────────────────

VISION_PROMPT = """You are analyzing a comic book panel to plan word-balloon placement.

The panel will have word balloons added on top of it. Your job: identify the
exact regions of the image that are SAFE for balloon placement vs. regions
that contain faces (NEVER COVERABLE) or character bodies (avoidable but not forbidden).

Return STRICT JSON ONLY (no markdown fence, no commentary) matching this schema:

{
  "image_width":   <int>,
  "image_height":  <int>,
  "faces": [
    {
      "label":  "<descriptor like 'bald captain' or 'character_a'>",
      "bbox":   [x0, y0, x1, y1],
      "confidence": <0.0-1.0>
    }
  ],
  "bodies": [
    { "label": "...", "bbox": [x0, y0, x1, y1] }
  ],
  "combadges": [
    {
      "owner":  "<descriptor of who's wearing it, must match a face label>",
      "point":  [x, y]
    }
  ],
  "preexisting_text_or_balloons": [
    { "label": "<what it is>", "bbox": [x0, y0, x1, y1] }
  ],
  "empty_regions": [
    {
      "bbox":     [x0, y0, x1, y1],
      "quality":  "excellent" | "good" | "acceptable",
      "note":     "brief description, e.g. 'dark space above viewscreen'"
    }
  ]
}

RULES:
- Bounding boxes are in absolute pixel coordinates (x0,y0 = top-left; x1,y1 = bottom-right).
- "faces" — be precise. The bbox MUST tightly enclose the ACTUAL visible face pixels
  in this specific image. Do NOT estimate where you think faces "should" be based
  on typical comic compositions. Look at the rendered image and report what is
  actually drawn. Be GENEROUS with padding (include forehead, chin, ears, and
  10-15px of margin) but base it on the real face position.
- If you're unsure whether something is a face, include it.
- "combadges" — Star Trek characters wear a delta-shaped Starfleet combadge on the
  LEFT side of the chest. Return the center point (x, y) of each visible combadge.
  This is where radio/comm balloon tails will anchor. If no combadge is visible
  on a given character, omit them from this list.
- "preexisting_text_or_balloons" — if the image itself contains a speech balloon,
  caption box, or any rendered text, report its bbox here. We must NOT place new
  balloons on top of these. If there are none, return an empty list.
- "empty_regions" must be large enough to plausibly contain a balloon (at least 200x100 px).
  CRITICAL: empty regions must have at least 30px of margin from the panel edge — do not
  return regions that are flush against any image edge.
- Order empty_regions from most-preferred (top-left, large) to least-preferred.
- Quality: 'excellent' = solid color or starfield; 'good' = busy but no faces; 'acceptable' = some detail to overlap.

Return ONLY the JSON object. Do not write any explanation, analysis,
preamble, or commentary. Your entire response must be parseable as JSON
starting with `{` and ending with `}`. Do not wrap in markdown fences.

EXAMPLE valid response (your exact format):
{
  "image_width": 2688,
  "image_height": 1536,
  "faces": [
    {"label": "bald_captain", "bbox": [600, 200, 900, 500], "confidence": 0.95}
  ],
  "bodies": [
    {"label": "bald_captain_body", "bbox": [500, 500, 1000, 1400]}
  ],
  "combadges": [
    {"owner": "bald_captain", "point": [750, 700]}
  ],
  "preexisting_text_or_balloons": [],
  "empty_regions": [
    {"bbox": [50, 50, 600, 400], "quality": "excellent", "note": "starfield upper-left"}
  ]
}"""


@dataclass
class PanelAnalysis:
    width:  int
    height: int
    face_bboxes:    list[tuple[int, int, int, int]]
    body_bboxes:    list[tuple[int, int, int, int]]
    combadges:      list[tuple[int, int]]    # (x, y) center points
    preexisting_bboxes: list[tuple[int, int, int, int]]
    empty_regions:  list[tuple[tuple[int, int, int, int], str, str]]
    # original full response from the model
    raw: dict


def analyze_panel(image_path: Path,
                  model: str = "minimax/minimax-m3") -> PanelAnalysis:
    """Call vision model via OpenRouter. Returns parsed PanelAnalysis.

    Default model is minimax/minimax-m3 per Eric's call 2026-06-02 —
    Claude Opus was returning phantom face bboxes on starfields and
    missing actual character faces on cel-shaded comic art. Worth
    re-evaluating periodically as models change.
    """
    key = _load_openrouter_key()

    img_bytes = Path(image_path).read_bytes()

    # Recraft sometimes returns WebP bytes inside a .png-named file.
    # Detect the actual format and either send proper MIME or transcode.
    if img_bytes[:4] == b"RIFF" and img_bytes[8:12] == b"WEBP":
        # Transcode to PNG so Claude / OpenAI vision endpoints accept it
        from io import BytesIO
        from PIL import Image as _Img
        buf = BytesIO()
        _Img.open(BytesIO(img_bytes)).convert("RGB").save(buf, "PNG")
        img_bytes = buf.getvalue()

    img_b64 = base64.b64encode(img_bytes).decode()

    body = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": VISION_PROMPT},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                },
            ],
        }],
        "max_tokens": 2000,
        "temperature": 0.0,
    }

    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/Eric90403/star-trek-graph",
            "X-Title": "star-trek-graph comic intelligence",
        },
    )

    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read())

    text = data["choices"][0]["message"]["content"]
    if text is None:
        # Some models (incl. minimax/minimax-m3 occasionally) return content=None
        # when the response is in 'reasoning' or 'reasoning_content' field instead.
        msg = data["choices"][0]["message"]
        text = msg.get("reasoning_content") or msg.get("reasoning") or ""
        if not text:
            raise ValueError(
                f"Vision model returned no content. Full message: {str(msg)[:500]}"
            )

    # Extract JSON object even if model wrapped in markdown fence.
    # Some vision models (notably minimax) sometimes write prose preamble
    # before the JSON. We use a balanced-brace extractor that scans the
    # text for the FIRST { ... matching } block, ignoring earlier braces
    # inside prose.
    text_stripped = text.strip()
    # Try markdown fence first
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text_stripped, re.DOTALL)
    json_str = None
    if fence_match:
        json_str = fence_match.group(1)
    else:
        # Find balanced { ... } block. Iterate over each '{' and find its
        # matching '}'. Try parsing each — pick the first one that parses.
        for i, ch in enumerate(text_stripped):
            if ch != "{":
                continue
            depth = 0
            for j in range(i, len(text_stripped)):
                c = text_stripped[j]
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = text_stripped[i:j + 1]
                        try:
                            json.loads(candidate)
                            json_str = candidate
                            break
                        except json.JSONDecodeError:
                            break  # this candidate failed; try next '{'
            if json_str:
                break

        if json_str is None:
            # No parseable JSON block found anywhere in the response.
            raise ValueError(
                f"No parseable JSON object found in vision response. "
                f"First 500 chars: {text_stripped[:500]}"
            )

    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError as e:
        debug_path = Path("/tmp/vision_response_debug.txt")
        debug_path.write_text(
            f"=== Raw response ===\n{text}\n\n=== Extracted JSON candidate ===\n{json_str}\n"
        )
        raise ValueError(
            f"JSON decode error at {e.pos}: {e.msg}. "
            f"Saved raw response to {debug_path}. "
            f"First 300 chars: {json_str[:300]}"
        ) from e

    # Get actual image dimensions for coordinate-scale normalization.
    # Vision models often report image_width/image_height that differ from
    # the actual file dimensions (e.g. MiniMax M3 reports 1920x1080 when
    # the actual image is 2688x1536, because the model internally resamples).
    # We scale all bboxes from reported-coords to actual-coords.
    from PIL import Image as _Img
    with _Img.open(image_path) as _opened:
        actual_w, actual_h = _opened.size

    reported_w = int(parsed.get("image_width", actual_w)) or actual_w
    reported_h = int(parsed.get("image_height", actual_h)) or actual_h
    scale_x = actual_w / reported_w if reported_w else 1.0
    scale_y = actual_h / reported_h if reported_h else 1.0

    def _bb(b):
        # Scale from reported coords to actual image coords.
        bb = b["bbox"][:4]
        return (
            int(bb[0] * scale_x),
            int(bb[1] * scale_y),
            int(bb[2] * scale_x),
            int(bb[3] * scale_y),
        )

    return PanelAnalysis(
        width  = actual_w,
        height = actual_h,
        face_bboxes = [_bb(f) for f in parsed.get("faces", [])],
        body_bboxes = [_bb(b) for b in parsed.get("bodies", [])],
        combadges = [
            (int(c["point"][0] * scale_x), int(c["point"][1] * scale_y))
            for c in parsed.get("combadges", [])
            if "point" in c and len(c["point"]) >= 2
        ],
        preexisting_bboxes = [_bb(p) for p in
                               parsed.get("preexisting_text_or_balloons", [])],
        empty_regions = [
            (_bb(e), e.get("quality", "acceptable"), e.get("note", ""))
            for e in parsed.get("empty_regions", [])
        ],
        raw = parsed,
    )


# ── Geometry helpers ─────────────────────────────────────────────────────────

def _rect_overlap(a: tuple[int, int, int, int],
                  b: tuple[int, int, int, int]) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0]
                or a[3] <= b[1] or b[3] <= a[1])


def _line_crosses_rect(p0: tuple[float, float],
                       p1: tuple[float, float],
                       rect: tuple[int, int, int, int]) -> bool:
    """Does line segment p0→p1 cross axis-aligned rect?"""
    x0, y0, x1, y1 = rect
    # Endpoints inside rect → cross
    for (x, y) in (p0, p1):
        if x0 <= x <= x1 and y0 <= y <= y1:
            return True
    # Check intersection with each edge
    def seg_intersect(a, b, c, d):
        # a-b and c-d intersect?
        def ccw(p, q, r):
            return (r[1] - p[1]) * (q[0] - p[0]) > (q[1] - p[1]) * (r[0] - p[0])
        return ccw(a, c, d) != ccw(b, c, d) and ccw(a, b, c) != ccw(a, b, d)
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    edges = [(corners[i], corners[(i + 1) % 4]) for i in range(4)]
    for (e0, e1) in edges:
        if seg_intersect(p0, p1, e0, e1):
            return True
    return False


def _rect_inside_rect(small: tuple[int, int, int, int],
                       big:   tuple[int, int, int, int]) -> bool:
    return (small[0] >= big[0] and small[1] >= big[1]
            and small[2] <= big[2] and small[3] <= big[3])


def _rect_inflate(r: tuple[int, int, int, int], pad: int):
    return (r[0] - pad, r[1] - pad, r[2] + pad, r[3] + pad)


# ── Balloon position search ─────────────────────────────────────────────────

@dataclass
class BalloonPlacement:
    cx: int
    cy: int
    score: float                  # higher is better
    rect: tuple[int, int, int, int]
    reason: str                   # debug — why this was chosen


def find_balloon_position(
    panel_bbox: tuple[int, int, int, int],   # absolute coords of the panel on page
    balloon_w: int,
    balloon_h: int,
    face_bboxes: list[tuple[int, int, int, int]],
    body_bboxes: list[tuple[int, int, int, int]],
    empty_regions: list[tuple[tuple[int, int, int, int], str, str]],
    speaker_anchor: Optional[tuple[float, float]] = None,
    prior_balloons: Optional[list[tuple[int, int, int, int]]] = None,
    preexisting_bboxes: Optional[list[tuple[int, int, int, int]]] = None,
    face_pad: int = 10,
    edge_margin: int = 30,
) -> Optional[BalloonPlacement]:
    """Search candidate centers, score by constraints.

    Hard vetoes:
      1. Balloon rect must fit inside panel (with edge_margin)
      2. Balloon rect must NOT overlap any face bbox (with padding)
      3. Tail center→anchor must NOT cross any face EXCEPT the speaker's
         own face (the one nearest the anchor). The speaker's face is the
         intended tail terminus; crossing it is required.
      4. Balloon must NOT overlap any prior balloon
      5. Balloon must NOT overlap any pre-existing balloon/text in the source art

    Soft scoring:
      + 100 base
      + landing inside an empty_region: +60/+30/+10 by quality
      + reading-order preserved with prior_balloons
      - body overlap area (light penalty)
    """
    if prior_balloons is None:
        prior_balloons = []
    if preexisting_bboxes is None:
        preexisting_bboxes = []

    panel_x0, panel_y0, panel_x1, panel_y1 = panel_bbox
    pad_faces = [_rect_inflate(f, face_pad) for f in face_bboxes]
    # Identify the SPEAKER's face — the one closest to the anchor — which
    # is exempt from the tail-crossing veto.
    speaker_face_idx = -1
    if speaker_anchor and pad_faces:
        ax, ay = speaker_anchor
        def _dist_to_face(fi):
            f = pad_faces[fi]
            fcx = (f[0] + f[2]) / 2
            fcy = (f[1] + f[3]) / 2
            return (fcx - ax) ** 2 + (fcy - ay) ** 2
        speaker_face_idx = min(range(len(pad_faces)), key=_dist_to_face)
        # Only count it as 'the speaker's face' if anchor is reasonably
        # close to that face (else off-panel anchors get treated wrong).
        sf = pad_faces[speaker_face_idx]
        if not (sf[0] - 50 <= ax <= sf[2] + 50 and
                sf[1] - 50 <= ay <= sf[3] + 50):
            speaker_face_idx = -1

    # Shrink panel by edge_margin so balloons never touch the frame
    safe_panel = (panel_x0 + edge_margin, panel_y0 + edge_margin,
                  panel_x1 - edge_margin, panel_y1 - edge_margin)

    # Sample grid of candidate centers across the panel
    candidates = []
    GRID_STEP = 30
    for cx in range(panel_x0 + balloon_w // 2,
                    panel_x1 - balloon_w // 2 + 1,
                    GRID_STEP):
        for cy in range(panel_y0 + balloon_h // 2,
                        panel_y1 - balloon_h // 2 + 1,
                        GRID_STEP):
            candidates.append((cx, cy))

    # Bias: also explicitly try the centers of any empty_regions
    for (er_bbox, _, _) in empty_regions:
        ecx = (er_bbox[0] + er_bbox[2]) // 2
        ecy = (er_bbox[1] + er_bbox[3]) // 2
        candidates.append((ecx, ecy))

    # Bias: explicitly try positions adjacent to the speaker (above, below,
    # left, right) at varying distances. This is where production balloons
    # typically sit.
    if speaker_anchor:
        ax, ay = speaker_anchor
        for dy in (-150, -120, -90, -200, -250):
            for dx in (-200, -120, -60, 0, 60, 120, 200):
                candidates.append((int(ax + dx), int(ay + dy)))

    best: Optional[BalloonPlacement] = None
    debug_top: list[tuple[float, int, int, str]] = []  # (score, cx, cy, reason)
    for cx, cy in candidates:
        rect = (cx - balloon_w // 2, cy - balloon_h // 2,
                cx + balloon_w // 2, cy + balloon_h // 2)

        # Hard veto 1: panel containment with edge margin
        if not _rect_inside_rect(rect, safe_panel):
            continue
        # Hard veto 2: face overlap
        if any(_rect_overlap(rect, f) for f in pad_faces):
            continue
        # Hard veto 3: tail crosses face (except the speaker's own face)
        if speaker_anchor:
            crossing = False
            for fi, f in enumerate(pad_faces):
                if fi == speaker_face_idx:
                    continue
                if _line_crosses_rect((cx, cy), speaker_anchor, f):
                    crossing = True
                    break
            if crossing:
                continue
        # Hard veto 4: overlap prior balloons we already placed
        if any(_rect_overlap(rect, pb) for pb in prior_balloons):
            continue
        # Hard veto 5: overlap pre-existing text/balloons in the source art
        if any(_rect_overlap(rect, pb) for pb in preexisting_bboxes):
            continue

        # Soft scoring — distance to speaker is the DOMINANT factor.
        # Production comic balloons sit close to their speaker, not floating
        # in negative space across the panel.
        score = 0.0

        # Distance-to-speaker is dominant.
        # Score peaks at distance ~0, decays to 0 at distance ~600.
        if speaker_anchor:
            ax, ay = speaker_anchor
            dist = math.hypot(cx - ax, cy - ay)
            score += max(0.0, 300.0 - dist / 2.0)

        # Bonus for landing in an empty region
        for (er_bbox, quality, _) in empty_regions:
            if _rect_inside_rect(rect, er_bbox):
                score += {"excellent": 50.0,
                          "good":      25.0,
                          "acceptable": 10.0}.get(quality, 0.0)
                break

        # Penalty for body overlap (light — bodies are coverable)
        body_overlap = 0
        for b in body_bboxes:
            ox = max(0, min(rect[2], b[2]) - max(rect[0], b[0]))
            oy = max(0, min(rect[3], b[3]) - max(rect[1], b[1]))
            body_overlap += ox * oy
        score -= body_overlap / 4000.0

        # Reading-order bonus: prefer above-and-left of next prior balloon
        if prior_balloons:
            last = prior_balloons[-1]
            last_cy = (last[1] + last[3]) / 2
            if cy > last_cy:
                score += 8.0

        # Slight top-bias for first balloon (balloons read top-to-bottom)
        if not prior_balloons:
            depth = (cy - panel_y0) / max(1, panel_y1 - panel_y0)
            score += (1.0 - depth) * 15.0

        reason = "ok"
        debug_top.append((score, cx, cy, reason))
        if best is None or score > best.score:
            best = BalloonPlacement(cx=cx, cy=cy, score=score,
                                     rect=rect, reason=reason)

    if best is not None and len(face_bboxes) > 0:
        # Surface the top 5 candidates for diagnosis
        debug_top.sort(key=lambda t: -t[0])
        print(f"      [placer] best 5 candidates:")
        for sc, cx, cy, _ in debug_top[:5]:
            print(f"        score={sc:7.1f}  ({cx},{cy})")

    return best


# ── Pretty debug summary ─────────────────────────────────────────────────────

def analysis_summary(a: PanelAnalysis) -> str:
    lines = [
        f"  Image:           {a.width}x{a.height}",
        f"  Faces:           {len(a.face_bboxes)}",
        f"  Bodies:          {len(a.body_bboxes)}",
        f"  Empty regions:   {len(a.empty_regions)}",
    ]
    for i, f in enumerate(a.face_bboxes[:6]):
        lines.append(f"    face {i}: {f}")
    for i, (er, q, note) in enumerate(a.empty_regions[:6]):
        lines.append(f"    empty {i} ({q}): {er} — {note}")
    return "\n".join(lines)


# ── Reading-order placer (Task 3) ────────────────────────────────────────────
#
# Replaces the broken Opus-iteration approach where radio balloons were
# placed near the LISTENER (because the speaker was off-panel) instead
# of in reading-order position.
#
# Design: data/COMIC_PIPELINE_DESIGN.md §4
# Rules: data/COMIC_BEST_PRACTICES.md §2, §3
#
# Key changes from the spiral:
#   - Iterates script.sorted_lines() — script order IS reading order
#   - For RADIO lines: no speaker anchor at all; position is reading-order
#     zone + empty region bonus only
#   - Comb-badge-as-anchor logic is GONE
#   - Width-retry loop on top of zone-based candidate generation


class PlacementError(Exception):
    """Raised when a balloon cannot be placed safely (no valid candidates
    after all retries). Carries the offending line + reason for the
    orchestrator to act on (retry with composition guidance, edit script,
    or surface to user)."""
    def __init__(self, line_order: int, line_speaker: str, reason: str):
        self.line_order = line_order
        self.line_speaker = line_speaker
        self.reason = reason
        super().__init__(
            f"Cannot place balloon for line {line_order} "
            f"({line_speaker or 'no-speaker'}): {reason}"
        )


def _reading_order_zone(
    line_order: int,
    total_lines: int,
    panel_bbox: tuple[int, int, int, int],
) -> tuple[int, int, int, int]:
    """Return the (x0, y0, x1, y1) zone for this line in the panel.

    Line 1: upper-left zone (full top, slight left bias).
    Last line: lower-right zone (full bottom, slight right bias).
    Middle lines: full-width band at appropriate height.

    Per BBP §2 Rule 2: Western readers read top-to-bottom, left-to-right.
    The placer biases candidates into the expected zone for each line
    so balloons follow the implied reading trail.
    """
    px0, py0, px1, py1 = panel_bbox
    pw, ph = px1 - px0, py1 - py0

    if total_lines == 1:
        # Single line: upper-center zone (full top half)
        return (px0 + int(pw * 0.15), py0, px1 - int(pw * 0.15), py0 + int(ph * 0.5))

    # Multi-line: divide panel into vertical bands, one per line
    band_height = ph / total_lines
    band_y0 = int(py0 + (line_order - 1) * band_height)
    band_y1 = int(py0 + line_order * band_height)

    if line_order == 1:
        # Top band, slight left bias — first balloon, reading-order priority
        return (px0, band_y0, px0 + int(pw * 0.7), band_y1)
    elif line_order == total_lines:
        # Bottom band, slight right bias — last balloon, lower-right priority
        return (px0 + int(pw * 0.3), band_y0, px1, band_y1)
    else:
        # Middle bands: full width
        return (px0, band_y0, px1, band_y1)


def _estimate_balloon_size(
    text: str,
    is_radio: bool,
    max_text_w: int = 700,
    font_size: int = 56,
    padding_x: int = 28,
    padding_y: int = 22,
    chars_per_line: int = 18,  # rough estimate for Komika Text at 56pt
) -> tuple[int, int]:
    """Estimate balloon width and height from text length.

    Per BBP §2 Rule 9: pre-compute text dimensions BEFORE placing the
    balloon. This is a rough estimate — the actual wrap depends on
    word breaks. Used to seed the placement; the actual wrap happens
    in balloons.py at render time.

    Returns (width, height) in pixels at 2K source.
    """
    # Approximate chars per line based on max_text_w and font size
    # Komika Text Bold at 56pt is roughly 30-32px per char
    approx_chars_per_line = max(10, max_text_w // 32)
    n_lines = max(1, -(-len(text) // approx_chars_per_line))  # ceil division
    line_h = int(font_size * 1.05)  # LINE_HEIGHT_MUL
    height = n_lines * line_h + padding_y * 2
    # Width: cap at max_text_w + padding
    estimated_w = min(max_text_w, len(text) * 32) + padding_x * 2
    width = max(estimated_w, 200)  # floor: don't go below 200px
    return (width, height)


def _generate_zone_candidates(
    zone_bbox: tuple[int, int, int, int],
    balloon_w: int,
    balloon_h: int,
    grid_step: int = 40,
) -> list[tuple[int, int]]:
    """Generate candidate (cx, cy) centers within a zone bbox, snapped
    to a grid. Returns list of (cx, cy) tuples.
    """
    zx0, zy0, zx1, zy1 = zone_bbox
    candidates = []
    for cx in range(zx0 + balloon_w // 2, zx1 - balloon_w // 2 + 1, grid_step):
        for cy in range(zy0 + balloon_h // 2, zy1 - balloon_h // 2 + 1, grid_step):
            candidates.append((cx, cy))
    return candidates


def _face_centers(face_bboxes: list[tuple[int, int, int, int]]) -> list[tuple[float, float]]:
    """Return (cx, cy) for each face bbox."""
    return [((f[0] + f[2]) / 2, (f[1] + f[3]) / 2) for f in face_bboxes]


def _face_top_points(face_bboxes: list[tuple[int, int, int, int]]) -> list[tuple[float, float]]:
    """Return (cx, y_top) for each face bbox — the point at the TOP of the
    face, horizontally centered. This is the anchor for tail termination
    per design decision: tails approach from above and terminate just
    below face_top (~upper-forehead area, well outside the eye/mouth).

    Per data/COMIC_TECHNIQUES_RESEARCH.md §5 question 2 — using face_top
    rather than face_center prevents the bug where tail tip lands inside
    the speaker's face."""
    return [((f[0] + f[2]) / 2, f[1]) for f in face_bboxes]


def _nearest_panel_edge_point(
    target: tuple[float, float],
    panel_bbox: tuple[int, int, int, int],
    edge_margin: int = 30,
) -> tuple[float, float]:
    """Return the nearest panel edge point to the target.

    Used for off-panel / radio speakers. Per BBP convention,
    off-panel-speaker balloons butt against the panel border with their
    tail nearest the (imagined) speaker direction. With no actual
    direction information, we anchor to the panel edge nearest to the
    listener (if any) or the panel edge nearest to the target point.
    """
    tx, ty = target
    px0, py0, px1, py1 = panel_bbox
    # Distance to each edge
    d_left   = tx - (px0 + edge_margin)
    d_right  = (px1 - edge_margin) - tx
    d_top    = ty - (py0 + edge_margin)
    d_bottom = (py1 - edge_margin) - ty
    min_d = min(d_left, d_right, d_top, d_bottom)
    if min_d == d_top:
        return (tx, py0 + edge_margin)
    elif min_d == d_bottom:
        return (tx, py1 - edge_margin)
    elif min_d == d_left:
        return (px0 + edge_margin, ty)
    else:
        return (px1 - edge_margin, ty)


def _speaker_face_for_line(
    line: ScriptLine,
    face_bboxes: list[tuple[int, int, int, int]],
    speaker_positions: Optional[dict[str, str]] = None,
) -> Optional[tuple[float, float]]:
    """Return the speaker's face TOP point (cx, y_top) for tail anchoring.

    For NORMAL lines: speaker is in panel; return face_top of speaker.
    For RADIO lines: returns None — radio balloons have NO tail; the
        placement is biased by listener position separately
        (see _listener_face_for_radio).

    Returns None when no faces in panel or speaker can't be identified.
    """
    if line.line_type == LineType.RADIO:
        return None  # No tail on radio balloons
    if not face_bboxes:
        return None
    tops = _face_top_points(face_bboxes)
    if speaker_positions and line.speaker in speaker_positions:
        pos = speaker_positions[line.speaker]
        if pos == "left":
            return min(tops, key=lambda c: c[0])
        elif pos == "right":
            return max(tops, key=lambda c: c[0])
        elif pos == "center":
            # Pick the face closest to the horizontal middle
            return min(tops, key=lambda c: abs(c[0] - 728))  # 1456/2
    # Default: leftmost face (BBP §2 Rule 3 — left character speaks first)
    return min(tops, key=lambda c: c[0])


def _listener_face_for_radio(
    line: ScriptLine,
    face_bboxes: list[tuple[int, int, int, int]],
    speaker_positions: Optional[dict[str, str]] = None,
) -> Optional[tuple[float, float]]:
    """For a RADIO line, return the LISTENER's face top — the on-panel
    character receiving the call. Used to bias the radio balloon's
    position (place above the listener per BBP convention), even though
    the balloon itself has NO tail.

    Per data/COMIC_TECHNIQUES_RESEARCH.md §3.3: when a specific on-panel
    character is clearly receiving the call, place the radio balloon
    ABOVE that character. The inline `Speaker via Comms:` prefix removes
    the spatial-misattribution risk that earlier killed this approach.

    Returns None when listener not specified or not in panel.
    """
    if line.line_type != LineType.RADIO:
        return None
    if not face_bboxes:
        return None
    tops = _face_top_points(face_bboxes)
    # Look up listener position in speaker_positions
    if line.listener and speaker_positions and line.listener in speaker_positions:
        pos = speaker_positions[line.listener]
        if pos == "left":
            return min(tops, key=lambda c: c[0])
        elif pos == "right":
            return max(tops, key=lambda c: c[0])
        elif pos == "center":
            return min(tops, key=lambda c: abs(c[0] - 728))
    # No clear listener mapping — fall through to no bias (placer uses
    # script-order zone only).
    return None


def _speaker_zone_candidates(
    speaker_anchor: tuple[float, float],
    panel_bbox: tuple[int, int, int, int],
    balloon_w: int,
    balloon_h: int,
    side_bias: str = "above",  # "above", "above_left", "above_right"
) -> list[tuple[int, int]]:
    """Generate candidate balloon centers near the speaker, primarily
    ABOVE but with side fallbacks for when the speaker is high in the
    frame.

    Per data/COMIC_TECHNIQUES_RESEARCH.md §3.2 — balloon position is
    speaker-anchored. Candidates form a fan above + to the side of
    the speaker's face_top, with optional left/right bias.

    For a LEFT-side speaker: bias candidates above-and-left.
    For a RIGHT-side speaker: bias candidates above-and-right.
    For an unbiased speaker: directly above.

    Includes side-of-face candidates so the placer can find a spot
    when the speaker is too high in the frame for above-only.
    """
    ax, ay = speaker_anchor
    px0, py0, px1, py1 = panel_bbox
    pw = px1 - px0
    candidates = []
    UP_RANGE_MIN = 80
    UP_RANGE_MAX = 350
    GRID = 35

    # Determine which direction has more room — push balloons that way.
    # If speaker is near the LEFT edge, balloons must extend RIGHTWARD.
    # If speaker is near the RIGHT edge, balloons must extend LEFTWARD.
    # The side_bias hint suggests preferred direction but room dictates.
    room_left = ax - (px0 + 30 + balloon_w // 2)
    room_right = (px1 - 30 - balloon_w // 2) - ax

    # 1. ABOVE the speaker (preferred zone)
    for dy_up in range(UP_RANGE_MIN, UP_RANGE_MAX + 1, GRID):
        cy = int(ay - dy_up - balloon_h // 2)
        if cy < py0 + 30 + balloon_h // 2:
            continue
        # Pick x_offsets based on which side has room. If room is asymmetric,
        # bias candidates toward the side with more space.
        if room_left > room_right + 100:
            # Lots of room left, little right → push LEFTWARD
            x_offsets = (-300, -200, -120, -60, 0)
        elif room_right > room_left + 100:
            # Lots of room right, little left → push RIGHTWARD
            x_offsets = (0, 60, 120, 200, 300)
        elif side_bias == "above_left":
            x_offsets = (-200, -120, -60, 0, 60)
        elif side_bias == "above_right":
            x_offsets = (-60, 0, 60, 120, 200)
        else:
            x_offsets = (-150, -75, 0, 75, 150)
        for dx in x_offsets:
            cx = int(ax + dx)
            if cx - balloon_w // 2 < px0 + 30:
                continue
            if cx + balloon_w // 2 > px1 - 30:
                continue
            candidates.append((cx, cy))

    # 2. TO THE SIDE of the speaker (when above is too high — e.g. when
    # speaker's face is close to the panel top). Use the direction with
    # MORE ROOM (not just side_bias).
    SIDE_RANGE_MIN = 100
    SIDE_RANGE_MAX = 500
    for dx_side in range(SIDE_RANGE_MIN, SIDE_RANGE_MAX + 1, GRID):
        if room_left > room_right:
            candidate_dxs = (-dx_side,)
        elif room_right > room_left:
            candidate_dxs = (dx_side,)
        else:
            candidate_dxs = (-dx_side, dx_side)
        for dx in candidate_dxs:
            cx = int(ax + dx)
            if cx - balloon_w // 2 < px0 + 30:
                continue
            if cx + balloon_w // 2 > px1 - 30:
                continue
            # cy range: align roughly with speaker's face vertical center
            # and slightly above.
            for dy in (-60, -20, 20, 60):
                cy = int(ay + dy)
                if cy < py0 + 30 + balloon_h // 2:
                    continue
                if cy > py1 - 30 - balloon_h // 2:
                    continue
                candidates.append((cx, cy))

    return candidates


def place_balloons_for_panel(
    panel_bbox: tuple[int, int, int, int],
    panel_analysis: PanelAnalysis,
    script: PanelScript,
    max_width_retry: int = 3,
    edge_margin: int = 30,
    face_pad: int = 10,
) -> list[BalloonPlacement]:
    """Place balloons for a panel using script reading order.

    Per data/COMIC_PIPELINE_DESIGN.md §4 (renumbered). Iterates
    script.sorted_lines() in order, places each balloon in its reading-
    order zone with hard vetoes (face protection, panel edge, prior
    balloon overlap) and soft scoring (zone bonus, speaker proximity
    for NORMAL only, empty region bonus, body overlap penalty).

    Args:
        panel_bbox: (x0, y0, x1, y1) absolute coords of the panel.
        panel_analysis: vision output with face_bboxes, body_bboxes,
            empty_regions, preexisting_bboxes.
        script: the PanelScript for this panel. Reading order comes
            from sorted_lines().
        max_width_retry: number of times to retry with narrower balloon
            if a placement fails (BBP Rule 10).
        edge_margin: balloon must be at least this many pixels from
            any panel edge.
        face_pad: face bbox is expanded by this for veto checks.

    Returns:
        list of BalloonPlacement, one per script line, in script order.

    Raises:
        PlacementError: if a balloon cannot be placed after width retries.
            The orchestrator can then decide whether to retry the art
            generation with composition guidance, or surface to the user.
    """
    panel_x0, panel_y0, panel_x1, panel_y1 = panel_bbox
    safe_panel = (
        panel_x0 + edge_margin,
        panel_y0 + edge_margin,
        panel_x1 - edge_margin,
        panel_y1 - edge_margin,
    )
    pad_faces = [_rect_inflate(f, face_pad) for f in panel_analysis.face_bboxes]
    preexisting = panel_analysis.preexisting_bboxes or []
    body_bboxes = panel_analysis.body_bboxes or []
    empty_regions = panel_analysis.empty_regions or []

    sorted_lines = script.sorted_lines()
    total_lines = len(sorted_lines)

    placements: list[BalloonPlacement] = []
    prior_rects: list[tuple[int, int, int, int]] = []

    for line in sorted_lines:
        is_radio = line.line_type == LineType.RADIO

        # Width-retry loop (BBP Rule 10). Try LARGEST first so balloons
        # use the full font size when room allows. Width retries only kick
        # in when the full-width balloon cannot find a valid placement —
        # at which point we narrow text and try again.
        text = line.text
        if is_radio and line.speaker:
            text = f"{line.speaker.title()} via Comms: {line.text}"
        width_multipliers = [1.0, 0.85, 0.7][:max_width_retry]

        placed: Optional[BalloonPlacement] = None
        last_attempt: Optional[BalloonPlacement] = None
        for width_mult in width_multipliers:
            bw, bh = _estimate_balloon_size(text, is_radio)
            bw = int(bw * width_mult)
            bh = int(bh * width_mult)

            # ── Identify the speaker (or listener for radio) ────────────
            # NORMAL line: speaker is in panel; face_top is the anchor.
            # RADIO line: speaker is off-panel; listener_anchor (if any)
            # biases the balloon position toward above the listener
            # (per BBP convention from research §3.3).
            speaker_anchor = _speaker_face_for_line(
                line,
                panel_analysis.face_bboxes,
                script.speaker_positions,
            )
            listener_anchor = _listener_face_for_radio(
                line,
                panel_analysis.face_bboxes,
                script.speaker_positions,
            )

            # Determine side bias from speaker_positions
            side_bias = "above"
            target_position = None
            if not is_radio and speaker_anchor and script.speaker_positions:
                target_position = script.speaker_positions.get(line.speaker)
            elif is_radio and listener_anchor and script.speaker_positions and line.listener:
                target_position = script.speaker_positions.get(line.listener)
            if target_position == "left":
                side_bias = "above_left"
            elif target_position == "right":
                side_bias = "above_right"

            # ── Build candidate positions ──────────────────────────────
            candidates: list[tuple[int, int]] = []

            # PRIMARY: speaker zone (above speaker for NORMAL, or above
            # listener for RADIO when listener is on-panel)
            primary_anchor = speaker_anchor if not is_radio else listener_anchor
            if primary_anchor:
                candidates.extend(
                    _speaker_zone_candidates(primary_anchor, panel_bbox,
                                              bw, bh, side_bias)
                )
                # For RADIO balloons, also generate candidates BELOW the
                # listener (panel-bottom fallback). The convention is
                # "above the listener" but when above is occupied by prior
                # balloons, below is the next-best, still proximate to
                # the listener for attribution.
                if is_radio:
                    lx, ly = primary_anchor
                    # below the face: face bottom is at y ≈ ly + face_height
                    # but we don't have the height here; use a fixed offset
                    below_y_start = int(ly + 320)  # below typical face
                    below_y_end = panel_y1 - edge_margin - bh // 2
                    for cy in range(below_y_start, below_y_end + 1, 40):
                        for dx in (-200, -120, -60, 0, 60, 120, 200):
                            cx = int(lx + dx)
                            if safe_panel[0] + bw // 2 <= cx <= safe_panel[2] - bw // 2:
                                candidates.append((cx, cy))

            # SECONDARY: top edge of the panel — useful for line 1 or
            # when speaker is low in the frame
            top_y = panel_y0 + edge_margin + bh // 2
            for cx in range(safe_panel[0] + bw // 2,
                            safe_panel[2] - bw // 2 + 1, 60):
                candidates.append((cx, top_y))

            # TERTIARY: empty region centers (good for both NORMAL and RADIO)
            for (er_bbox, _, _) in empty_regions:
                ecx = (er_bbox[0] + er_bbox[2]) // 2
                ecy = (er_bbox[1] + er_bbox[3]) // 2
                if (safe_panel[0] + bw // 2 <= ecx <= safe_panel[2] - bw // 2
                    and safe_panel[1] + bh // 2 <= ecy <= safe_panel[3] - bh // 2):
                    candidates.append((ecx, ecy))

            # FALLBACK: if no anchor (no faces at all in panel), generate
            # candidates across the upper third of the panel by line order
            if not candidates:
                upper_band_y = panel_y0 + edge_margin + bh // 2
                lower_y = panel_y0 + int((panel_y1 - panel_y0) * 0.6) - bh // 2
                step_y = max(40, (lower_y - upper_band_y) // 5)
                for cy in range(upper_band_y, lower_y + 1, step_y):
                    for cx in range(safe_panel[0] + bw // 2,
                                    safe_panel[2] - bw // 2 + 1, 80):
                        candidates.append((cx, cy))

            # ── Score and veto candidates ──────────────────────────────
            best: Optional[BalloonPlacement] = None
            for cx, cy in candidates:
                rect = (cx - bw // 2, cy - bh // 2,
                        cx + bw // 2, cy + bh // 2)

                # Hard veto 1: panel containment
                if not _rect_inside_rect(rect, safe_panel):
                    continue
                # Hard veto 2: face overlap (faces are sacred — zero pixels)
                if any(_rect_overlap(rect, f) for f in pad_faces):
                    continue
                # Hard veto 3: prior balloon overlap with 20px gutter
                BALLOON_GUTTER = 20
                if any(_rect_overlap(_rect_inflate(rect, BALLOON_GUTTER), pb)
                       for pb in prior_rects):
                    continue
                # Hard veto 4: preexisting text overlap
                if any(_rect_overlap(rect, pb) for pb in preexisting):
                    continue

                # Hard veto 5: Eddie Campbell test — for NORMAL lines, the
                # balloon must be CLOSER to the intended speaker's face than
                # to any other face. Otherwise the reader will mis-assign it
                # per Campbell's Rule #3 ("a reader will read a balloon and
                # then read the next nearest balloon"). Sources:
                # data/COMIC_TECHNIQUES_RESEARCH.md §3.1.
                if not is_radio and speaker_anchor and len(panel_analysis.face_bboxes) > 1:
                    bx_center = (rect[0] + rect[2]) / 2
                    by_center = (rect[1] + rect[3]) / 2
                    sa_x, sa_y = speaker_anchor
                    dist_to_intended = math.hypot(bx_center - sa_x, by_center - sa_y)
                    misattributed = False
                    for face in panel_analysis.face_bboxes:
                        face_top_x = (face[0] + face[2]) / 2
                        face_top_y = face[1]
                        if abs(face_top_x - sa_x) < 1 and abs(face_top_y - sa_y) < 1:
                            continue  # skip the intended speaker's face
                        dist_to_other = math.hypot(bx_center - face_top_x,
                                                    by_center - face_top_y)
                        if dist_to_other < dist_to_intended:
                            misattributed = True
                            break
                    if misattributed:
                        continue  # veto: would be read as the wrong speaker

                # ── Soft scoring ──────────────────────────────────────
                score = 0.0

                # Speaker proximity (NORMAL only) — primary signal
                if speaker_anchor and not is_radio:
                    ax, ay = speaker_anchor
                    dist = math.hypot(cx - ax, cy - ay)
                    score += max(0.0, 300.0 - dist / 2.0)

                # Listener proximity (RADIO only) — bias above listener
                # per BBP §3.3 convention
                if listener_anchor and is_radio:
                    lx, ly = listener_anchor
                    dist = math.hypot(cx - lx, cy - ly)
                    score += max(0.0, 200.0 - dist / 3.0)

                # Reading-order CONSTRAINT bonus: balloon should be at or
                # below+right of the previous balloon (down or right).
                # This is the constraint, not a layout axis.
                if prior_rects:
                    prev_rect = prior_rects[-1]
                    prev_cx = (prev_rect[0] + prev_rect[2]) / 2
                    prev_cy = (prev_rect[1] + prev_rect[3]) / 2
                    # Bonus if below OR right of previous balloon
                    if cy >= prev_cy or cx >= prev_cx:
                        score += 40.0
                    else:
                        score -= 80.0  # penalty for upper-left of prior

                # Empty region bonus
                for (er_bbox, quality, _) in empty_regions:
                    if _rect_inside_rect(rect, er_bbox):
                        score += {"excellent": 50.0,
                                  "good": 25.0,
                                  "acceptable": 10.0}.get(quality, 0.0)
                        break

                # Body overlap penalty (light — Klein: torso is acceptable)
                body_overlap = 0
                for b in body_bboxes:
                    ox = max(0, min(rect[2], b[2]) - max(rect[0], b[0]))
                    oy = max(0, min(rect[3], b[3]) - max(rect[1], b[1]))
                    body_overlap += ox * oy
                score -= body_overlap / 4000.0

                # Top-bias for first line (line 1 sits high in reading order)
                if line.order == 1:
                    depth = (cy - panel_y0) / max(1, panel_y1 - panel_y0)
                    score += (1.0 - depth) * 30.0

                if best is None or score > best.score:
                    last_attempt = BalloonPlacement(
                        cx=cx, cy=cy, score=score, rect=rect,
                        reason=f"line{line.order}_{'radio' if is_radio else 'normal'}",
                    )
                    best = last_attempt

            if best is not None:
                placed = best
                break  # Found a valid placement, exit width-retry loop

        if placed is None:
            print(f"      [placer] FAILED on line {line.order} ({line.speaker})")
            print(f"      [placer] prior_rects={prior_rects}")
            print(f"      [placer] faces (padded)={pad_faces}")
            print(f"      [placer] balloon={bw}x{bh}")
            raise PlacementError(
                line.order, line.speaker,
                f"no valid candidate after {max_width_retry} width retries"
            )

        placements.append(placed)
        prior_rects.append(placed.rect)

    return placements


# Re-export for convenience
__all__ = [
    "PanelAnalysis",
    "BalloonPlacement",
    "analyze_panel",
    "find_balloon_position",  # legacy — kept for backward compat
    "analysis_summary",
    "place_balloons_for_panel",  # new reading-order placer (Task 3)
    "PlacementError",
]
