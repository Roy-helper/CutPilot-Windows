"""CutPilot — Web UI launcher via pywebview.

Opens a native window rendering the Vue 3 + Tailwind frontend.
Python backend functions are exposed to JavaScript via the pywebview API bridge.
"""
from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

# ── Logging setup: console + rotating file ──────────────────
_LOG_DIR = Path.home() / ".cutpilot" / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_LOG_FILE = _LOG_DIR / "cutpilot.log"

_file_handler = TimedRotatingFileHandler(
    str(_LOG_FILE), when="midnight", backupCount=7, encoding="utf-8",
)
_file_handler.setFormatter(logging.Formatter(
    "%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
))
logging.basicConfig(level=logging.INFO, handlers=[
    logging.StreamHandler(),
    _file_handler,
])

# Fix SSL certificates for PyInstaller on macOS
try:
    import certifi
    import os
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
except ImportError:
    pass


def main():
    from core.window import main as _main
    _main(log_file=_LOG_FILE)


if __name__ == "__main__":
    main()
