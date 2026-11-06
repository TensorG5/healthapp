"""Используется Docker HEALTHCHECK: код выхода 0 = здоров, 1 = нет."""
import os
import sys
import urllib.request

port = os.getenv("APP_PORT", "8080")
try:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as r:
        sys.exit(0 if r.status == 200 else 1)
except Exception:
    sys.exit(1)
