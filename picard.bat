@echo off
REM Talk to Picard (alias for: trek.bat --character PICARD)
.venv\Scripts\python.exe src\character_agent.py --character PICARD %*
