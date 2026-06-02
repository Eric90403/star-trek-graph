#!/usr/bin/env bash
# install.sh — Star Trek Graph project installer (Linux / macOS)
# Usage: bash install.sh

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'  # no colour

info()  { echo -e "${GREEN}[install]${NC} $*"; }
warn()  { echo -e "${YELLOW}[warn]${NC}   $*"; }
error() { echo -e "${RED}[error]${NC}  $*" >&2; }

# ── 1. Check Python version ───────────────────────────────────────────────────

PYTHON=""
for candidate in python3.11 python3.12 python3.13 python3 python; do
    if command -v "$candidate" &>/dev/null; then
        version=$("$candidate" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 11 ]; then
            if [ "$minor" -ge 14 ]; then
                warn "Python $version detected. pydantic-core may not build on 3.14+."
                warn "If installation fails, install Python 3.11 via pyenv:"
                warn "  curl https://pyenv.run | bash"
                warn "  pyenv install 3.11.9 && pyenv local 3.11.9"
            fi
            PYTHON="$candidate"
            info "Using Python $version ($candidate)"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    error "Python 3.11+ not found."
    error "Install it from https://python.org or via pyenv:"
    error "  curl https://pyenv.run | bash"
    error "  pyenv install 3.11.9 && pyenv local 3.11.9"
    exit 1
fi

# ── 2. Create virtualenv ──────────────────────────────────────────────────────

if [ -d ".venv" ]; then
    info ".venv already exists — skipping creation"
else
    info "Creating .venv..."
    "$PYTHON" -m venv .venv
fi

info "Installing dependencies from requirements.txt..."
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r requirements.txt

# ── 3. Docker images ──────────────────────────────────────────────────────────

if command -v docker &>/dev/null; then
    info "Pulling Docker images (docker compose pull)..."
    docker compose pull || warn "docker compose pull failed — images may already be cached."
else
    warn "Docker not found. Install Docker Desktop from https://docker.com"
    warn "Then run: docker compose pull"
fi

# ── 4. Next steps ─────────────────────────────────────────────────────────────

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  Installation complete. Next steps:"
echo ""
echo "  1. Set your Anthropic API key:"
echo "       export ANTHROPIC_API_KEY=sk-ant-..."
echo "       (add to ~/.bashrc or ~/.zshrc to make it permanent)"
echo ""
echo "  2. Start the database:"
echo "       docker compose up -d"
echo ""
echo "  3. Load TNG episodes (first time only — takes ~10 min):"
echo "       .venv/bin/python scripts/ingest_tng.py"
echo ""
echo "  4. Build embeddings (first time only — takes ~7 min on CPU):"
echo "       .venv/bin/python src/embedder.py"
echo ""
echo "  5. Talk to a character:"
echo "       ./trek                        # Picard (default)"
echo "       ./trek --character WORF"
echo "       ./trek --character DATA --top-k 60"
echo ""
echo "  Neo4j Browser: http://localhost:7475"
echo "  Bolt:          bolt://localhost:7688  (user: neo4j, pass: trekgraph)"
echo "═══════════════════════════════════════════════════════════════"
