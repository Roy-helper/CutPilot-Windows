"""CutPilot configuration via pydantic-settings.

All settings can be overridden with environment variables prefixed ``CUTPILOT_``
or via a ``.env`` file in the project root.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings


class CutPilotConfig(BaseSettings):
    """CutPilot global configuration."""

    model_config = {"env_prefix": "CUTPILOT_", "env_file": ".env", "frozen": True}

    # DeepSeek API
    api_key: str = ""
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model: str = "deepseek-v3"

    # Processing
    max_versions: int = 3
    min_sentences: int = 15
    generate_fast: bool = True

    # Output
    output_dir: str = ""
