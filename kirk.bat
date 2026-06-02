@echo off
REM Talk to Kirk (alias for: trek.bat --character KIRK --series TOS)
.venv\Scripts\python.exe src\character_agent.py --character KIRK --series TOS %*
