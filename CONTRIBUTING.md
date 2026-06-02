# Contributing to Star Trek Graph

First — thanks for being here. This is a fan-research project; the bar
for contributing is "show up." If you're a Star Trek nerd who also writes
software, you'll fit right in.

## Ways to help

**Ingest new corpora.** DS9 scripts are all available on st-minutiae.com
in the 400-series numbering. TNG films, partial VOY, and ENT pilots are
also there. Each new series only needs a tiny tweak to `scripts/fetch_*.py`
to pull. The parser is series-agnostic.

**Normalise locations.** The graph currently has BRIDGE, MAIN BRIDGE,
and ENTERPRISE BRIDGE as separate Location nodes. We need a
`data/location_aliases.yaml` mapping raw scene-heading strings to a
canonical (Setting, Place, Region) triple. See the open TODO in
`docs/ONTOLOGY.md`.

**Build behavioral cards** (Layer 2). For the top ~30 characters, use
the retrieved-dialogue corpus to draft `BehavioralCard` nodes — speech
patterns, decision heuristics, hard limits. This is Phase 3 in
`docs/PLAN.md`.

**Improve the parser.** Edge cases exist. If you find an episode that
parses thin (< 50 lines), that's a parser bug — open an issue with the
script ID and we'll fix the state machine.

**The Episode Writer** (Phase 5). This is the headline feature: a
multi-agent writer's room that uses the graph as canon bible. Big lift,
big payoff. If you have multi-agent harness experience, this is the
contribution that would make this project legendary.

## Development workflow

```bash
git clone https://github.com/Eric90403/star-trek-graph
cd star-trek-graph
bash install.sh                     # creates .venv and installs deps
docker compose up -d                # starts Neo4j

# Set credentials (one of these)
export ANTHROPIC_API_KEY=sk-ant-...  # any user
# OR run Hermes Agent locally — auth.py will pick up ~/.hermes/auth.json

# Build the corpus
python scripts/ingest_tng.py       # ~5 min, no API calls
python src/embedder.py             # ~10–60 min depending on hardware

# Talk to a character
./trek
```

## Code conventions

- **Imports**: stdlib → third-party → local (with `# noqa: E402` if you
  must reorder for `sys.path` reasons).
- **Style**: ~90-char lines, type hints where they help, docstrings on
  public functions.
- **No hardcoded paths or credentials.** Use `src/config.py` and add a
  new `TREK_*` env var if you need a new tunable.
- **No `length()` on strings or lists in Cypher.** Use `size()`. Neo4j
  5+ reserves `length()` for paths only.
- **MERGE, not CREATE.** All graph writes must be idempotent.
- **Local-first.** Don't introduce paid APIs without a clear reason
  and a documented opt-out. Embeddings are local (nomic). The LLM is
  the only commercial dependency.

## Testing

```bash
.venv/bin/pytest tests/
```

Add a test for any non-trivial parser or graph-loader change. The
existing `tests/test_parser.py` is a sketch — add to it freely.

## Pull request checklist

- [ ] Code compiles (`python -m py_compile src/*.py`).
- [ ] `pytest` passes.
- [ ] New env vars (if any) are documented in `src/config.py` and `README.md`.
- [ ] `CHANGELOG.md` gets a line under `[Unreleased]`.
- [ ] Star Trek references in commit messages are encouraged but optional.

## Filing issues

Good bug reports include:
- The script ID(s) involved (e.g. 175 for "Best of Both Worlds II")
- Output of `docker ps` and `python --version`
- The full traceback
- A Cypher query that demonstrates the issue, if relevant

## Code of conduct

Be kind. Star Trek's whole thing is "we figured out how to get along."
Behave accordingly.

## Project provenance

This project was designed and built in a single interactive session with
[Hermes Agent](https://hermes-agent.nousresearch.com) running Claude Opus.
That doesn't make it precious — change anything you like.
