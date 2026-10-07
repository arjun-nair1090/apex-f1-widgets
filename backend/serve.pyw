"""Run the APEX backend with no console window (Task Scheduler on Windows, a systemd user service on Linux).
Logs go to apex.log.

    .venv\\Scripts\\pythonw.exe serve.pyw     (Windows)
    .venv/bin/python serve.pyw              (Linux, macOS)
"""
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))  # .env, apex.db and apex.log live next to this file
sys.stdout = sys.stderr = open("apex.log", "a", buffering=1, encoding="utf-8")  # pythonw has no console

import uvicorn  # noqa: E402

uvicorn.run("apex.main:app", host="127.0.0.1", port=8077)
