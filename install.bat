@echo off
REM install.bat — Star Trek Graph project installer (Windows)
REM Usage: install.bat  (run from the project root)

setlocal enabledelayedexpansion

echo.
echo [install] Star Trek Graph — Windows installer
echo.

REM ── 1. Check Python ──────────────────────────────────────────────────────────

set PYTHON=
for %%P in (python3.11 python3 python) do (
    if not defined PYTHON (
        where %%P >nul 2>&1
        if not errorlevel 1 (
            for /f "delims=" %%V in ('%%P -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2^>nul') do (
                set "PYVER=%%V"
            )
            set "PYTHON=%%P"
        )
    )
)

if not defined PYTHON (
    echo [error] Python 3.11+ not found.
    echo         Download from https://python.org/downloads/
    echo         Or install via winget: winget install Python.Python.3.11
    exit /b 1
)

echo [install] Using Python %PYVER% ^(%PYTHON%^)

REM Warn on 3.14+
for /f "tokens=2 delims=." %%M in ("%PYVER%") do (
    if %%M geq 14 (
        echo [warn] Python %PYVER% detected. pydantic-core may not build on 3.14+.
        echo [warn] If install fails, use Python 3.11 from https://python.org
    )
)

REM ── 2. Create virtualenv ─────────────────────────────────────────────────────

if exist ".venv" (
    echo [install] .venv already exists — skipping creation
) else (
    echo [install] Creating .venv...
    %PYTHON% -m venv .venv
)

echo [install] Installing dependencies from requirements.txt...
.venv\Scripts\python.exe -m pip install --upgrade pip -q
.venv\Scripts\pip.exe install -r requirements.txt

REM ── 3. Docker images ─────────────────────────────────────────────────────────

where docker >nul 2>&1
if not errorlevel 1 (
    echo [install] Pulling Docker images...
    docker compose pull
    if errorlevel 1 (
        echo [warn] docker compose pull failed — images may already be cached.
    )
) else (
    echo [warn] Docker not found. Install Docker Desktop from https://docker.com
    echo [warn] Then run: docker compose pull
)

REM ── 4. Next steps ────────────────────────────────────────────────────────────

echo.
echo ================================================================
echo   Installation complete. Next steps:
echo.
echo   1. Set your Anthropic API key (PowerShell):
echo        $env:ANTHROPIC_API_KEY = 'sk-ant-...'
echo.
echo      Or permanently via System Properties ^> Environment Variables
echo.
echo   2. Start the database:
echo        docker compose up -d
echo.
echo   3. Load TNG episodes (first time only -- takes ~10 min):
echo        .venv\Scripts\python.exe scripts\ingest_tng.py
echo.
echo   4. Build embeddings (first time only -- takes ~7 min on CPU):
echo        .venv\Scripts\python.exe src\embedder.py
echo.
echo   5. Talk to a character:
echo        trek                        (Picard, default)
echo        trek --character WORF
echo        trek --character DATA --top-k 60
echo.
echo   Neo4j Browser: http://localhost:7475
echo   Bolt:          bolt://localhost:7688  (user: neo4j / pass: trekgraph)
echo ================================================================
echo.

endlocal
