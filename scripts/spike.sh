#!/usr/bin/env bash
# One-shot spike orchestrator: venv -> deps -> fetch -> parse -> load -> summary.
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
echo "[spike] root=$ROOT"

PY="${PY:-}"
if [ -z "$PY" ]; then
  for cand in python3.12 python3.11 python3.13 python3; do
    if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
  done
fi
echo "[spike] using $PY ($($PY --version))"
if [ ! -d .venv ]; then
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo "[spike] waiting for Neo4j bolt on 7688..."
for i in $(seq 1 60); do
  if (echo > /dev/tcp/localhost/7688) >/dev/null 2>&1; then
    echo "  bolt is up"
    break
  fi
  sleep 1
done

echo "[spike] fetch"
python scripts/fetch_scripts.py

echo "[spike] parse"
PYTHONPATH=src python src/parser.py

echo "[spike] load"
PYTHONPATH=src python src/loader.py

echo "[spike] sample query: top 5 characters by line count"
python - <<'PY'
import os
from neo4j import GraphDatabase
d = GraphDatabase.driver(os.environ.get("NEO4J_URI", "bolt://localhost:7688"),
                          auth=(os.environ.get("NEO4J_USER","neo4j"),
                                os.environ.get("NEO4J_PASSWORD","trekgraph")))
with d.session() as s:
    r = s.run("MATCH (c:Character)<-[:SPOKEN_BY]-(l:Line) "
              "RETURN c.canonical_name AS name, count(l) AS lines "
              "ORDER BY lines DESC LIMIT 5")
    for row in r:
        print(f"  {row['name']:20s} {row['lines']}")
d.close()
PY

echo "[spike] done"
