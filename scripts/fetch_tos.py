#!/usr/bin/env python3
"""Fetch TOS transcripts from chakoteya.net.

URL pattern: http://chakoteya.net/StarTrek/{N}.htm
Production numbers: 1..79 plus the oddball "16b" (Menagerie Part 2).

Saves files as data/raw/tos_{N}.htm.  Polite: 1.5s delay between
requests, identifies itself in the User-Agent, skips files already on
disk.  Idempotent — safe to re-run.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import config  # noqa: E402

RAW_DIR = ROOT / "data" / "raw"
BASE_URL = "http://chakoteya.net/StarTrek/{n}.htm"
USER_AGENT = ("star-trek-graph/0.2 fan-research "
              "(github.com/Eric90403/star-trek-graph)")
DELAY = 1.5

# Production numbers — 1..79 plus 16b (Menagerie Part 2)
TOS_IDS: list[str] = (
    [str(i) for i in range(1, 17)]
    + ["16b"]
    + [str(i) for i in range(17, 80)]
)


def fetch_all(ids: list[str] | None = None,
              skip_existing: bool = True,
              delay: float = DELAY) -> tuple[list[str], list[str], list[tuple[str, str]]]:
    ids = ids if ids is not None else TOS_IDS
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    downloaded: list[str] = []
    skipped: list[str] = []
    failed: list[tuple[str, str]] = []

    headers = {"User-Agent": USER_AGENT}
    for n in ids:
        dest = RAW_DIR / f"tos_{n}.htm"
        if skip_existing and dest.exists() and dest.stat().st_size > 500:
            skipped.append(n)
            print(f"  skip  tos_{n} (already exists)")
            continue
        url = BASE_URL.format(n=n)
        try:
            r = httpx.get(url, timeout=30, headers=headers,
                          follow_redirects=True)
            if r.status_code == 200 and len(r.text) > 500:
                # chakoteya pages are latin-1 / windows-1252-ish; httpx
                # generally guesses fine but force a re-encode via .text
                dest.write_text(r.text, encoding="utf-8")
                downloaded.append(n)
                print(f"  ✓ tos_{n}  ({len(r.text):,} chars)")
            else:
                failed.append((n, f"HTTP {r.status_code} / {len(r.text)}B"))
                print(f"  ✗ tos_{n}  HTTP {r.status_code}")
        except Exception as e:
            failed.append((n, str(e)))
            print(f"  ✗ tos_{n}  {e}")
        time.sleep(delay)

    print(f"\nFetch: downloaded={len(downloaded)} "
          f"skipped={len(skipped)} failed={len(failed)}")
    if failed:
        for n, reason in failed:
            print(f"  FAIL tos_{n}: {reason}")
    return downloaded, skipped, failed


if __name__ == "__main__":
    fetch_all()
