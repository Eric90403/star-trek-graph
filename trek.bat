@echo off
REM trek.bat — GraphRAG character chatbot launcher (Windows)
REM Usage: trek [--character WORF] [--top-k 40]
"%~dp0.venv\Scripts\python.exe" "%~dp0src\character_agent.py" %*
