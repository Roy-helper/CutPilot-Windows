"""Processing history for CutPilot.

Records every video processing run with timestamp, results, and output paths.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_HISTORY_PATH = Path.home() / ".cutpilot" / "history.json"
_MAX_ENTRIES = 500  # Keep last 500 entries


class HistoryEntry:
    """Single processing history record."""

    def __init__(
        self,
        video_name: str,
        video_path: str,
        timestamp: str,
        success: bool,
        error: str = "",
        versions_count: int = 0,
        output_files: list[str] | None = None,
        approach_tags: list[str] | None = None,
        duration_sec: float = 0.0,
    ):
        self.video_name = video_name
        self.video_path = video_path
        self.timestamp = timestamp
        self.success = success
        self.error = error
        self.versions_count = versions_count
        self.output_files = output_files or []
        self.approach_tags = approach_tags or []
        self.duration_sec = duration_sec

    def to_dict(self) -> dict[str, Any]:
        """Serialize entry to a plain dict."""
        return {
            "video_name": self.video_name,
            "video_path": self.video_path,
            "timestamp": self.timestamp,
            "success": self.success,
            "error": self.error,
            "versions_count": self.versions_count,
            "output_files": list(self.output_files),
            "approach_tags": list(self.approach_tags),
            "duration_sec": self.duration_sec,
        }


def load_history() -> list[dict[str, Any]]:
    """Load history entries from JSON file."""
    if not _HISTORY_PATH.exists():
        return []
    try:
        with open(_HISTORY_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, IOError) as exc:
        logger.warning("Failed to load history: %s", exc)
        return []


def save_history(entries: list[dict[str, Any]]) -> None:
    """Save history entries to JSON file (keeps last _MAX_ENTRIES)."""
    trimmed = entries[-_MAX_ENTRIES:]
    _HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(trimmed, f, ensure_ascii=False, indent=2)


def add_history_entry(entry: HistoryEntry) -> None:
    """Append a new entry to history."""
    entries = load_history()
    entries.append(entry.to_dict())
    save_history(entries)


def clear_history() -> None:
    """Clear all history entries."""
    save_history([])
