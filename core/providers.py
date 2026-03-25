"""AI model provider presets for CutPilot.

Users select a provider from a dropdown; base_url and model name
are filled in automatically. Only API Key needs to be entered.
"""
from __future__ import annotations

from pydantic import BaseModel


class ProviderPreset(BaseModel):
    """Immutable AI provider configuration."""

    model_config = {"frozen": True}

    id: str              # internal key
    name: str            # display name in UI (Chinese)
    base_url: str
    model: str
    api_key_hint: str    # placeholder text for API key input


# Ordered list — first one is the default
PROVIDERS: tuple[ProviderPreset, ...] = (
    ProviderPreset(
        id="deepseek",
        name="DeepSeek",
        base_url="https://api.deepseek.com/v1",
        model="deepseek-chat",
        api_key_hint="sk-... (从 platform.deepseek.com 获取)",
    ),
    ProviderPreset(
        id="qwen",
        name="通义千问 (阿里云百炼)",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model="qwen-plus",
        api_key_hint="sk-... (从 bailian.console.aliyun.com 获取)",
    ),
    ProviderPreset(
        id="kimi",
        name="Kimi (月之暗面)",
        base_url="https://api.moonshot.cn/v1",
        model="moonshot-v1-8k",
        api_key_hint="sk-... (从 platform.moonshot.cn 获取)",
    ),
    ProviderPreset(
        id="minimax",
        name="MiniMax",
        base_url="https://api.minimax.chat/v1",
        model="MiniMax-Text-01",
        api_key_hint="eyJ... (从 platform.minimaxi.com 获取)",
    ),
    ProviderPreset(
        id="zhipu",
        name="智谱 ChatGLM",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        model="glm-4-flash",
        api_key_hint="从 open.bigmodel.cn 获取",
    ),
    ProviderPreset(
        id="custom",
        name="自定义 (OpenAI 兼容)",
        base_url="",
        model="",
        api_key_hint="输入 API Key",
    ),
)

DEFAULT_PROVIDER_ID = PROVIDERS[0].id


def get_provider(provider_id: str) -> ProviderPreset | None:
    """Look up a provider by ID."""
    for p in PROVIDERS:
        if p.id == provider_id:
            return p
    return None


def get_provider_names() -> list[tuple[str, str]]:
    """Return list of (id, display_name) for UI dropdown."""
    return [(p.id, p.name) for p in PROVIDERS]
