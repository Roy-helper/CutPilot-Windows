"""CutPilot configuration via pydantic-settings.

All settings can be overridden with environment variables prefixed ``CUTPILOT_``
or via a ``.env`` file in the project root.
"""
from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings


class CutPilotConfig(BaseSettings):
    """CutPilot global configuration."""

    model_config = {"env_prefix": "CUTPILOT_", "env_file": ".env", "frozen": True}

    # AI provider
    provider: str = "deepseek"
    api_key: str = ""
    base_url: str = "https://api.deepseek.com/v1"
    model: str = "deepseek-chat"

    # Processing
    max_versions: int = 3
    min_sentences: int = 15
    generate_fast: bool = True

    # Hook overlay
    enable_hook_overlay: bool = True
    hook_duration: float = 3.0

    # Speaker diarization
    enable_speaker_diarization: bool = True

    # Video quality preset
    # - draft: fast encode, lower quality (CRF 28, ultrafast) — for preview
    # - standard: balanced (CRF 23, medium) — default for most users
    # - high: best quality (CRF 18, slow) — for final delivery
    video_quality: Literal["draft", "standard", "high"] = "standard"

    # Output
    output_dir: str = ""


# Quality presets mapped to FFmpeg parameters
QUALITY_PRESETS: dict[str, dict[str, str]] = {
    "draft": {"crf": "28", "preset": "ultrafast"},
    "standard": {"crf": "23", "preset": "medium"},
    "high": {"crf": "18", "preset": "slow"},
}
