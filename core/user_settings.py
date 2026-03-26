"""User-editable settings persisted to ~/.cutpilot/settings.json.

These override CutPilotConfig defaults. The GUI writes here;
CutPilotConfig reads from .env but user_settings takes precedence.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from core.config import CutPilotConfig
from core.providers import get_provider

logger = logging.getLogger(__name__)

_SETTINGS_DIR = Path.home() / ".cutpilot"
_SETTINGS_PATH = _SETTINGS_DIR / "settings.json"

_DEFAULTS: dict[str, Any] = {
    "provider": "deepseek",
    "api_key": "",
    "base_url": "",       # only used when provider="custom"
    "model": "",          # only used when provider="custom"
    "max_versions": 3,
    "min_sentences": 15,
    "generate_fast": True,
    "enable_hook_overlay": True,
    "hook_duration": 3.0,
    "enable_speaker_diarization": True,
    "video_quality": "standard",
    "output_dir": "",
    "hotwords": "",
}


def load_user_settings() -> dict[str, Any]:
    """Load settings from JSON, returning defaults for missing keys."""
    settings = dict(_DEFAULTS)
    settings["_settings_corrupted"] = False
    if not _SETTINGS_PATH.exists():
        return settings
    try:
        raw = _SETTINGS_PATH.read_text(encoding="utf-8")
        stored = json.loads(raw)
        if not isinstance(stored, dict):
            logger.warning("settings.json root is not a dict, using defaults")
            settings["_settings_corrupted"] = True
            return settings
        for key in _DEFAULTS:
            if key in stored:
                settings[key] = stored[key]
        return settings
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load settings.json: %s", exc)
        settings["_settings_corrupted"] = True
        return settings


def save_user_settings(settings: dict[str, Any]) -> None:
    """Save settings dict to JSON file."""
    try:
        _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        payload = {k: v for k, v in settings.items() if k in _DEFAULTS}
        _SETTINGS_PATH.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        logger.error("Failed to save settings.json: %s", exc)
        raise


def build_config_from_settings() -> CutPilotConfig:
    """Build a CutPilotConfig using user settings as overrides.

    Priority: user_settings.json > .env > defaults.

    When provider is not "custom", base_url and model are resolved
    from the provider preset, ignoring any stored base_url / model.
    """
    settings = load_user_settings()
    provider_id = settings.get("provider", "deepseek")
    preset = get_provider(provider_id)

    # Resolve base_url / model from preset unless custom
    resolved = dict(settings)
    if preset is not None and preset.id != "custom":
        resolved["base_url"] = preset.base_url
        resolved["model"] = preset.model

    # Only pass non-empty string values and all non-string values
    kwargs: dict[str, Any] = {}
    for key, value in resolved.items():
        if key not in CutPilotConfig.model_fields:
            continue
        if isinstance(value, str) and value == "":
            continue
        kwargs[key] = value
    return CutPilotConfig(**kwargs)
