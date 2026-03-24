"""CutPilot pipeline — orchestrates the full video processing flow.

ASR → Director (script generation) → Inspector (quality review) → Editor (cutting)

Each stage is cached so failed runs can resume from the last successful step.
Progress is reported via an optional callback.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Callable

from core.cache_manager import CacheManager
from core.config import CutPilotConfig
from core.models import ProcessResult, Sentence, ScriptVersion

logger = logging.getLogger(__name__)


async def process_video(
    video_path: Path,
    config: CutPilotConfig,
    on_progress: Callable[[str, int], None] | None = None,
    cache: CacheManager | None = None,
    hotwords: str = "",
) -> ProcessResult:
    """Process a single video through the full pipeline.

    Steps:
        1. ASR — transcribe video to sentences (cached)
        2. Director — generate script versions via AI (cached)
        3. Inspector — quality review + dedup (cached)
        4. Editor — cut video into final outputs

    Args:
        video_path: Path to the source video file.
        config: CutPilot configuration.
        on_progress: Optional callback ``(stage_label, percent)`` for UI.
        cache: Optional cache manager (auto-created if None).
        hotwords: Space-separated hotwords for ASR boosting.

    Returns:
        ProcessResult with success status, approved versions, and output files.
    """
    if cache is None:
        cache = CacheManager()

    video_path = Path(video_path)
    if not video_path.exists():
        return ProcessResult(success=False, error=f"视频文件不存在: {video_path}")

    try:
        # Step 1: ASR
        sentences = await _run_asr(video_path, config, cache, hotwords, on_progress)
        if len(sentences) < config.min_sentences:
            return ProcessResult(
                success=False,
                error=f"素材太短（{len(sentences)}句，需要至少{config.min_sentences}句）",
            )

        # Step 2: Director
        versions = await _run_director(sentences, config, cache, video_path, on_progress)
        if not versions:
            return ProcessResult(success=False, error="AI 编导未生成有效版本")

        # Step 3: Inspector
        approved = await _run_inspector(
            versions, sentences, config, cache, video_path, on_progress,
        )
        if not approved:
            return ProcessResult(success=False, error="所有版本未通过质检")

        # Step 4: Editor
        output_files = await _run_editor(
            video_path, approved, sentences, config, cache, on_progress,
        )

        _report_progress(on_progress, "完成", 100)
        return ProcessResult(
            success=True,
            versions=approved,
            output_files=output_files,
        )
    except Exception as exc:
        logger.exception("Pipeline failed for %s", video_path)
        return ProcessResult(success=False, error=str(exc))


# ---------------------------------------------------------------------------
# Stage runners with caching
# ---------------------------------------------------------------------------


async def _run_asr(
    video_path: Path,
    config: CutPilotConfig,
    cache: CacheManager,
    hotwords: str,
    on_progress: Callable[[str, int], None] | None,
) -> list[Sentence]:
    """Run ASR with caching."""
    _report_progress(on_progress, "正在识别语音...", 10)

    if cache.exists(video_path, "asr"):
        logger.info("Loading ASR from cache")
        raw = cache.load(video_path, "asr")
        return [Sentence(**s) for s in raw]

    from core.asr import transcribe_video

    segments = await transcribe_video(str(video_path), hotwords=hotwords)
    sentences = [
        Sentence(
            id=i + 1,
            start_sec=seg.start,
            end_sec=seg.end,
            text=seg.text,
            speaker_id=getattr(seg, "speaker", None),
        )
        for i, seg in enumerate(segments)
    ]

    cache.save(video_path, "asr", [s.model_dump() for s in sentences])
    logger.info("ASR complete: %d sentences", len(sentences))
    return sentences


async def _run_director(
    sentences: list[Sentence],
    config: CutPilotConfig,
    cache: CacheManager,
    video_path: Path,
    on_progress: Callable[[str, int], None] | None,
) -> list[ScriptVersion]:
    """Run AI director with caching."""
    _report_progress(on_progress, "AI 正在生成脚本...", 35)

    if cache.exists(video_path, "director"):
        logger.info("Loading director results from cache")
        raw = cache.load(video_path, "director")
        return [ScriptVersion(**v) for v in raw]

    from core.director import generate_versions

    versions = await generate_versions(
        sentences, config, version_count=config.max_versions,
    )

    cache.save(video_path, "director", [v.model_dump() for v in versions])
    logger.info("Director complete: %d versions", len(versions))
    return versions


async def _run_inspector(
    versions: list[ScriptVersion],
    sentences: list[Sentence],
    config: CutPilotConfig,
    cache: CacheManager,
    video_path: Path,
    on_progress: Callable[[str, int], None] | None,
) -> list[ScriptVersion]:
    """Run inspector with caching."""
    _report_progress(on_progress, "AI 正在质检...", 55)

    if cache.exists(video_path, "inspector"):
        logger.info("Loading inspector results from cache")
        raw = cache.load(video_path, "inspector")
        return [ScriptVersion(**v) for v in raw]

    from core.inspector import review_versions

    approved = await review_versions(versions, sentences, config)

    cache.save(video_path, "inspector", [v.model_dump() for v in approved])
    logger.info("Inspector complete: %d approved", len(approved))
    return approved


async def _run_editor(
    video_path: Path,
    approved: list[ScriptVersion],
    sentences: list[Sentence],
    config: CutPilotConfig,
    cache: CacheManager,
    on_progress: Callable[[str, int], None] | None,
) -> list[dict]:
    """Run editor (no caching — always regenerate video files)."""
    _report_progress(on_progress, "正在剪辑视频...", 70)

    from core.editor import cut_versions

    output_files = await cut_versions(video_path, approved, sentences, config)
    logger.info("Editor complete: %d output files", len(output_files))
    return output_files


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _report_progress(
    callback: Callable[[str, int], None] | None,
    label: str,
    percent: int,
) -> None:
    """Fire progress callback if provided."""
    if callback is not None:
        callback(label, percent)


def generate_copy_text(versions: list[ScriptVersion]) -> str:
    """Generate the combined copy text file content for all versions.

    Format per version:
        === V{n} [{approach_tag}] ===
        发布文案: ...
        封面主标题: ...
        封面副标题: ...
        标签: #tag1 #tag2 ...
    """
    blocks: list[str] = []
    for v in versions:
        tag_label = f" [{v.approach_tag}]" if v.approach_tag else ""
        block = (
            f"=== V{v.version_id}{tag_label} ===\n"
            f"发布文案: {v.publish_text}\n"
            f"封面主标题: {v.cover_title}\n"
            f"封面副标题: {v.cover_subtitle}\n"
            f"标签: {' '.join(v.tags)}"
        )
        blocks.append(block)
    return "\n\n".join(blocks) + "\n"
