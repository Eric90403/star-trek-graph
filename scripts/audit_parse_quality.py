#!/usr/bin/env python3
"""
scripts/audit_parse_quality.py — Survey parser output across the full corpus.

Reports:
  - Episodes with missing or malformed titles
  - Episodes with thin dialogue counts (potential parse failures)
  - Episodes with extremely thin scene counts
  - Top "speakers" that look like parsing noise (one-word, all-caps stage directions)
  - Distribution histograms

Usage:
    python scripts/audit_parse_quality.py
    python scripts/audit_parse_quality.py --write-report docs/PARSE_AUDIT.md
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT     = Path(__file__).parent.parent
JSON_DIR = ROOT / "data" / "parsed"


def load_episodes():
    eps = []
    for jf in sorted(JSON_DIR.glob("*.json")):
        with jf.open() as f:
            eps.append(json.load(f))
    return eps


def audit(eps, out=sys.stdout):
    say = lambda *a, **kw: print(*a, file=out, **kw)

    say("# Parse Quality Audit\n")
    say(f"**Corpus:** {len(eps)} episodes\n")

    # ── Title hygiene ─────────────────────────────────────────────────────────
    say("## Title hygiene\n")
    bad_titles = []
    for e in eps:
        t = e.get("title") or ""
        problems = []
        if not t:
            problems.append("EMPTY")
        if len(t) > 60:
            problems.append(f"TOO LONG ({len(t)} chars)")
        if "\n" in t:
            problems.append("CONTAINS NEWLINE")
        if any(junk in t.upper() for junk in
               ("WRITTEN BY", "DIRECTED BY", "COPYRIGHT", "DRAFT", "#40")):
            problems.append("CONTAINS HEADER JUNK")
        if problems:
            bad_titles.append((e.get("id"), t[:60], problems))

    if bad_titles:
        say(f"**{len(bad_titles)} episodes with title problems:**\n")
        say("| ID | Title (excerpt) | Issues |")
        say("|----|-----------------|--------|")
        for eid, t, probs in bad_titles[:25]:
            t_disp = t.replace("\n", " \\n ")
            say(f"| {eid} | `{t_disp}` | {', '.join(probs)} |")
        if len(bad_titles) > 25:
            say(f"\n_({len(bad_titles) - 25} more...)_")
    else:
        say("All titles clean ✅")
    say()

    # ── Line-count distribution ──────────────────────────────────────────────
    say("## Dialogue line count distribution\n")
    counts = sorted((len(e.get("lines", [])) for e in eps))
    n = len(counts)
    say(f"- Min: {counts[0]}")
    say(f"- p10: {counts[n//10]}")
    say(f"- p50: {counts[n//2]}")
    say(f"- p90: {counts[(9*n)//10]}")
    say(f"- Max: {counts[-1]}")
    say(f"- Mean: {sum(counts) / n:.0f}\n")

    say("**Episodes with thin parses (<300 lines):**\n")
    thin = sorted(
        ((e.get("id"), e.get("title") or "?", len(e.get("lines", [])))
         for e in eps if len(e.get("lines", [])) < 300),
        key=lambda x: x[2],
    )
    if thin:
        say("| ID | Title | Lines |")
        say("|----|-------|-------|")
        for eid, t, n_lines in thin:
            t_disp = t.replace("\n", " ").strip()[:50]
            say(f"| {eid} | {t_disp} | {n_lines} |")
    else:
        say("None — all episodes parsed at >=300 lines ✅")
    say()

    # ── Scene-count distribution ─────────────────────────────────────────────
    say("## Scene count distribution\n")
    s_counts = sorted((len(e.get("scenes", [])) for e in eps))
    say(f"- Min: {s_counts[0]}")
    say(f"- p10: {s_counts[n//10]}")
    say(f"- p50: {s_counts[n//2]}")
    say(f"- Max: {s_counts[-1]}\n")

    very_thin_scenes = [(e["id"], e.get("title", "?"), len(e.get("scenes", [])))
                         for e in eps if len(e.get("scenes", [])) < 20]
    if very_thin_scenes:
        say(f"**{len(very_thin_scenes)} episodes with very few scenes (<20):**\n")
        for eid, t, n_scenes in sorted(very_thin_scenes, key=lambda x: x[2]):
            t_disp = (t or "").replace("\n", " ").strip()[:50]
            say(f"- {eid} `{t_disp}` — {n_scenes} scenes")
    say()

    # ── Suspicious speakers ──────────────────────────────────────────────────
    say("## Suspicious speaker names\n")
    speaker_counter = Counter()
    for e in eps:
        for ln in e.get("lines", []):
            speaker_counter[ln.get("speaker", "?")] += 1

    suspicious = []
    for sp, n in speaker_counter.items():
        if not sp or sp == "?":
            continue
        # Likely noise: contains common stage directions, very long, or weird chars
        if any(junk in sp for junk in (
            "FADE", "CUT TO", "DISSOLVE", "INT.", "EXT.", "OPTICAL",
            "ANGLE", "POV", "REVISED", "DRAFT", "TEASER", "END OF",
            "CONTINUED", "CREDITS",
        )):
            suspicious.append((sp, n))
        elif len(sp) > 35:
            suspicious.append((sp, n))

    if suspicious:
        say(f"**{len(suspicious)} suspicious speakers parsed as characters:**\n")
        for sp, n in sorted(suspicious, key=lambda x: -x[1])[:20]:
            say(f"- `{sp[:60]}`  ({n} lines)")
        if len(suspicious) > 20:
            say(f"\n_({len(suspicious) - 20} more...)_")
    else:
        say("No obvious parser-noise speakers ✅")
    say()

    # ── Warnings emitted by parser ───────────────────────────────────────────
    say("## Parser warnings\n")
    warnings = Counter()
    for e in eps:
        for w in e.get("warnings", []) or []:
            warnings[w] += 1
    if warnings:
        say("| Warning | Episodes |")
        say("|---------|----------|")
        for w, n in warnings.most_common():
            say(f"| {w} | {n} |")
    else:
        say("No warnings emitted ✅")
    say()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-report", type=str, default=None,
                    help="Write report to this file instead of stdout")
    args = ap.parse_args()

    eps = load_episodes()
    if args.write_report:
        path = Path(args.write_report)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as f:
            audit(eps, out=f)
        print(f"Audit written to {path}")
    else:
        audit(eps)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
