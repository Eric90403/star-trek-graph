#!/usr/bin/env python3
"""
Fetch all TNG scripts from st-minutiae.com.
IDs 102-277 = all 176 TNG episodes (episode number + 100 offset).
Skips files already downloaded. Polite: 1s delay between requests.
"""

import httpx
import time
import sys
from pathlib import Path

RAW_DIR    = Path(__file__).parent.parent / "data" / "raw"
BASE_URL   = "https://www.st-minutiae.com/resources/scripts/{id}.txt"
USER_AGENT = "star-trek-graph/1.0 fan-research project (github.com/Eric90403/star-trek-graph)"
TNG_IDS    = list(range(102, 278))   # 102–277 inclusive = 176 episodes
DELAY      = 1.0                     # seconds between requests

def fetch_all(ids=TNG_IDS, skip_existing=True, delay=DELAY):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    downloaded, skipped, failed = [], [], []

    for script_id in ids:
        dest = RAW_DIR / f"{script_id}.txt"
        if skip_existing and dest.exists():
            skipped.append(script_id)
            print(f"  skip  {script_id} (already exists)")
            continue

        url = BASE_URL.format(id=script_id)
        try:
            r = httpx.get(url, timeout=15,
                          headers={"User-Agent": USER_AGENT},
                          follow_redirects=True)
            if r.status_code == 200:
                dest.write_text(r.text, encoding="utf-8")
                downloaded.append(script_id)
                print(f"  ✓ {script_id}  ({len(r.text):,} chars)")
            else:
                failed.append((script_id, r.status_code))
                print(f"  ✗ {script_id}  HTTP {r.status_code}")
        except Exception as e:
            failed.append((script_id, str(e)))
            print(f"  ✗ {script_id}  ERROR: {e}")

        time.sleep(delay)

    print(f"\nDone. downloaded={len(downloaded)} skipped={len(skipped)} failed={len(failed)}")
    if failed:
        print(f"Failed IDs: {failed}")
    return downloaded, skipped, failed


if __name__ == "__main__":
    print(f"Fetching {len(TNG_IDS)} TNG scripts → {RAW_DIR}")
    fetch_all()
