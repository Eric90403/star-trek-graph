#!/usr/bin/env python3
"""Fetch TNG scripts from st-minutiae.com."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

SCRIPT_IDS = {
    102: "Encounter at Farpoint",
    103: "The Naked Now",
    175: "The Best of Both Worlds, Part 1",
    200: "Redemption (was-175 alt)",  # title resolved from header
    277: "All Good Things... Part 1",
}

URL = "https://www.st-minutiae.com/resources/scripts/{id}.txt"
UA = "trek-graph-spike/0.1 (research; contact: local)"


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    raw_dir = root / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    ok = 0
    with httpx.Client(headers={"User-Agent": UA}, timeout=30.0, follow_redirects=True) as c:
        for sid in SCRIPT_IDS:
            out = raw_dir / f"{sid}.txt"
            if out.exists() and out.stat().st_size > 1000:
                print(f"[skip] {sid} already present ({out.stat().st_size} bytes)")
                ok += 1
                continue
            url = URL.format(id=sid)
            print(f"[fetch] {sid} <- {url}")
            try:
                r = c.get(url)
                r.raise_for_status()
                out.write_text(r.text, encoding="utf-8")
                print(f"  ok ({len(r.text)} chars)")
                ok += 1
            except Exception as e:  # noqa: BLE001
                print(f"  FAIL: {e}", file=sys.stderr)
            time.sleep(1.0)
    print(f"Fetched {ok}/{len(SCRIPT_IDS)} scripts.")
    return 0 if ok == len(SCRIPT_IDS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
