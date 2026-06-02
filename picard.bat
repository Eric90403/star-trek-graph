@echo off
REM picard.bat — Picard legacy agent launcher (Windows)
REM Usage: picard [--character WORF]
"%~dp0.venv\Scripts\python.exe" "%~dp0src\picard_agent.py" %*
