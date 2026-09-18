@echo off
cd /d "C:\Users\gio\Desktop\VALIDAZIONE START-UP"
set PYTHONPATH=.
set LLM_MAX_CALLS_PER_RUN=400
".venv\Scripts\python.exe" -X utf8 -m scripts.adlib_local 4 >> adlib_local.log 2>&1
