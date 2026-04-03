"""Subprocess helpers for CutPilot — hides console windows on Windows.

On Windows, subprocess calls to ffmpeg/ffprobe pop up a black cmd window.
This module provides wrappers that suppress that window via CREATE_NO_WINDOW.
"""
from __future__ import annotations

import subprocess
import sys

# Windows-only: hide the console window spawned by subprocess
_STARTUP_FLAGS: dict = {}
if sys.platform == "win32":
    _STARTUP_FLAGS["creationflags"] = subprocess.CREATE_NO_WINDOW


def run_hidden(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """subprocess.run() that hides the console window on Windows."""
    return subprocess.run(cmd, **_STARTUP_FLAGS, **kwargs)


def popen_hidden(cmd: list[str], **kwargs) -> subprocess.Popen:
    """subprocess.Popen() that hides the console window on Windows."""
    return subprocess.Popen(cmd, **_STARTUP_FLAGS, **kwargs)
