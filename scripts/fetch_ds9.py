#!/usr/bin/env python3
"""
Fetch all available DS9 scripts from st-minutiae.com.

Source IDs 402-575 cover the 173 available DS9 scripts. ID 473 is missing
from the archive (Tears of the Prophets Pt II — 404s), so we skip it.

Files are saved as data/raw/ds9_{N}.txt to avoid collision with TNG's
data/raw/{N}.txt (TNG uses 102-277).

Polite: 1.0s delay between requests, skips files already downloaded.
"""
from __future__ import annotations

import time
from pathlib import Path

import httpx

RAW_DIR    = Path(__file__).parent.parent / "data" / "raw"
BASE_URL   = "https://www.st-minutiae.com/resources/scripts/{id}.txt"
USER_AGENT = "star-trek-graph/0.3 fan-research (github.com/Eric90403/star-trek-graph)"
DS9_IDS    = [i for i in range(402, 576) if i != 473]   # 173 episodes
DELAY      = 1.0   # seconds between requests


def fetch_all(ids=DS9_IDS, skip_existing: bool = True, delay: float = DELAY):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    downloaded, skipped, failed = [], [], []

    for script_id in ids:
        dest = RAW_DIR / f"ds9_{script_id}.txt"
        if skip_existing and dest.exists():
            skipped.append(script_id)
            print(f"  skip  ds9_{script_id} (already exists)")
            continue

        url = BASE_URL.format(id=script_id)
        try:
            r = httpx.get(url, timeout=15,
                          headers={"User-Agent": USER_AGENT},
                          follow_redirects=True)
            if r.status_code == 200:
                dest.write_text(r.text, encoding="utf-8")
                downloaded.append(script_id)
                print(f"  ✓ ds9_{script_id}  ({len(r.text):,} chars)")
            else:
                failed.append((script_id, r.status_code))
                print(f"  ✗ ds9_{script_id}  HTTP {r.status_code}")
        except Exception as e:
            failed.append((script_id, str(e)))
            print(f"  ✗ ds9_{script_id}  ERROR: {e}")

        time.sleep(delay)

    print(f"\nDone. downloaded={len(downloaded)} skipped={len(skipped)} failed={len(failed)}")
    if failed:
        print(f"Failed IDs: {failed}")
    return downloaded, skipped, failed


if __name__ == "__main__":
    print(f"Fetching {len(DS9_IDS)} DS9 scripts → {RAW_DIR}")
    fetch_all()
