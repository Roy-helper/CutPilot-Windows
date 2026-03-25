"""Resolve resource paths for both development and PyInstaller frozen mode."""
from __future__ import annotations

import sys
from pathlib import Path


def get_project_root() -> Path:
    """Return the project root directory.

    In development: the repo root (parent of core/).
    In PyInstaller bundle: the _MEIPASS temp directory.
    """
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent


def get_config_dir() -> Path:
    """Return path to the config/ directory."""
    return get_project_root() / "config"


def get_prompts_dir() -> Path:
    """Return path to config/prompts/ directory."""
    return get_config_dir() / "prompts"
