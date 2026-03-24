"""OpenAI-compatible AI client for CutPilot.

Adapted from VideoFactory4 — uses CutPilotConfig instead of VF4 Settings.
"""
from __future__ import annotations

import re

import httpx
from openai import OpenAI

from core.config import CutPilotConfig


def create_openai_client(
    config: CutPilotConfig | None = None,
    timeout: float = 300.0,
) -> OpenAI:
    """Create an OpenAI client configured for DashScope.

    Args:
        config: CutPilot configuration. Auto-loaded if None.
        timeout: Request timeout in seconds.

    Returns:
        Configured OpenAI client instance.
    """
    if config is None:
        config = CutPilotConfig()

    http_client = httpx.Client(
        trust_env=False,
        timeout=httpx.Timeout(timeout, connect=30.0),
    )

    return OpenAI(
        api_key=config.api_key,
        base_url=config.base_url,
        http_client=http_client,
        max_retries=5,
    )


def call_ai(
    prompt: str,
    system: str = "",
    config: CutPilotConfig | None = None,
    temperature: float = 0.3,
) -> str:
    """Send a text prompt to DeepSeek and return the cleaned response."""
    if config is None:
        config = CutPilotConfig()

    client = create_openai_client(config)

    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model=config.model,
        messages=messages,
        temperature=temperature,
    )

    raw = response.choices[0].message.content or ""
    return re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
