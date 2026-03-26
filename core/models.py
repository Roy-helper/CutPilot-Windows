"""Core data models for CutPilot.

Extracted from VideoFactory4 — only the models needed for the pipeline.
All models use frozen=True to enforce immutability.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


APPROACH_TAGS = {
    "痛点解决", "价格冲击", "使用场景", "材质工艺",
    "外观颜值", "功能对比", "人群锁定", "反常识",
}


class Sentence(BaseModel):
    """Immutable single sentence from ASR transcript with timing."""

    model_config = {"frozen": True}

    id: int
    start_sec: float
    end_sec: float
    text: str
    speaker_id: str | None = None


class ScriptVersion(BaseModel):
    """Immutable AI-selected sentence arrangement version."""

    model_config = {"frozen": True}

    version_id: int
    title: str = ""
    structure: str = ""
    sentence_ids: list[int] = Field(default_factory=list)
    reason: str = ""
    estimated_duration: float = 0.0
    score: float = 0.0
    publish_text: str = ""
    cover_title: str = ""
    cover_subtitle: str = ""
    tags: list[str] = Field(default_factory=list)
    approach_tag: str = ""

    @field_validator("approach_tag")
    @classmethod
    def validate_approach_tag(cls, v: str) -> str:
        if v and v not in APPROACH_TAGS:
            return ""
        return v


class ProcessResult(BaseModel):
    """Result of processing a single video."""

    model_config = {"frozen": True}

    success: bool
    error: str = ""
    versions: list[ScriptVersion] = Field(default_factory=list)
    output_files: list[dict] = Field(default_factory=list)


class ExportOptions(BaseModel):
    """User-selected export options per version.

    Controls what gets exported — hook overlay, speed variants, quality.
    Used by the UI to let users pick before export, instead of dumping
    everything.
    """

    model_config = {"frozen": True}

    version_id: int
    export_normal: bool = True
    export_fast: bool = False
    enable_hook: bool = False
    video_quality: str = "standard"  # draft / standard / high


