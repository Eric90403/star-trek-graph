# Contributing to Star Trek Graph

First — thanks for being here. This is a fan-research project; the bar
for contributing is "show up." If you're a Star Trek nerd who also writes
software, you'll fit right in.

## Ways to help

**Ingest new corpora.** TOS and DS9 are loaded as of v0.3.0.
**Voyager** is the obvious next target — chakoteya.net has complete
VOY transcripts in the same HTML format as TOS, so the existing
`src/tos_parser.py` can be adapted. The 4 **TNG Films** are also
available on st-minutiae.com in the same format as the TNG series
(would extend the Picard agent with film-era dialogue).

**Normalise locations.** The graph currently has BRIDGE, MAIN BRIDGE,
and ENTERPRISE BRIDGE as separate Location nodes. We need a
`data/location_aliases.yaml` mapping raw scene-heading strings to a
canonical (Setting, Place, Region) triple. See the open TODO in
`docs/ONTOLOGY.md`.

**Generate more behavioral cards.** v0.3.0 ships 20 cards for the top
characters. Extending to the next 30-40 characters (Garak's full
arc, Dukat, Q, Lwaxana, Barclay, Ro) would noticeably improve
Episode Writer voice quality for those agents. The orchestrator
(`scripts/build_behavioral_cards.py`) is idempotent — just add
to the top-N list and re-run.

**Improve the Episode Writer.** Some ideas:
- Local-LLM mode (Ollama, vLLM, llama.cpp) for the Scene Writers
  so people can generate episodes without an Anthropic key
- A `--continue` mode that picks up after the validator's
  feedback and lets the Showrunner revise before scenes are written
- Beat templates per series (the deferred Phase 4 work)
- Multi-episode arcs

**Frontends.** A web UI for `./trek` and `./write-episode` would
massively widen the audience. So would a Telegram or Discord bot
wrapping the agent.

**Improve the parser.** Edge cases exist. If you find an episode
that parses thin (< 300 dialogue lines for a screenplay or < 100
for a transcript), that's likely a parser bug — open an issue
with the script ID and we'll fix the state machine.

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

## Branch protection (what the rules actually are)

The `main` branch on this repo has protection enabled:

- **No direct pushes from contributors** — everything outside the
  maintainer's solo workflow goes through a PR.
- **CI must pass** before merge (syntax + import smoke tests on Linux,
  macOS, and Windows × Python 3.11 and 3.12).
- **At least one review** must approve the PR.
- **Stale reviews are dismissed** when new commits are pushed.
- **Conversation threads must be resolved** before merging.
- **No force-pushes**, no branch deletions.

(The repo owner retains bypass for solo housekeeping commits — small
doc tweaks, version bumps, badge fixes. Feature work goes through PR
regardless.)

These rules exist so that the release artifacts (sample episodes,
embedded corpus, validated agents) stay reproducible and the CI
badge in the README is honest. Working in a feature branch + PR is
the standard GitHub workflow and isn't extra friction.

If you're working on something experimental and want a sandbox,
**fork the repo** — your fork is yours to push to freely.

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
