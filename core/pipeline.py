"""CutPilot pipeline — orchestrates the full video processing flow.

ASR → Director (script generation) → Inspector (quality review) → Editor (cutting)

Each stage is cached so failed runs can resume from the last successful step.
Progress is reported via an optional callback.
"""
from __future__ import annotations

import asyncio
import logging
import threading
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
    cancel_event: threading.Event | None = None,
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
        cancel_event: Optional threading.Event to signal cancellation.

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
        if cancel_event and cancel_event.is_set():
            return ProcessResult(success=False, error="用户取消处理")
        sentences = await _run_asr(video_path, config, cache, hotwords, on_progress)
        if len(sentences) < config.min_sentences:
            return ProcessResult(
                success=False,
                error=f"素材太短（{len(sentences)}句，需要至少{config.min_sentences}句）",
            )

        # Export SRT subtitle alongside output
        try:
            base_output = Path(config.output_dir).expanduser() if config.output_dir else video_path.parent / "output"
            srt_dir = base_output / video_path.stem
            srt_dir.mkdir(parents=True, exist_ok=True)
            export_srt(sentences, srt_dir / f"{video_path.stem}.srt")
        except Exception:
            logger.warning("SRT export failed, continuing", exc_info=True)

        # Step 2: Director
        if cancel_event and cancel_event.is_set():
            return ProcessResult(success=False, error="用户取消处理")
        versions = await _run_director(sentences, config, cache, video_path, on_progress)
        if not versions:
            return ProcessResult(success=False, error="AI 编导未生成有效版本")

        # Step 3: Inspector
        if cancel_event and cancel_event.is_set():
            return ProcessResult(success=False, error="用户取消处理")
        approved = await _run_inspector(
            versions, sentences, config, cache, video_path, on_progress,
        )
        if not approved:
            return ProcessResult(success=False, error="所有版本未通过质检")

        # Step 4: Editor
        if cancel_event and cancel_event.is_set():
            return ProcessResult(success=False, error="用户取消处理")
        output_files = await _run_editor(
            video_path, approved, sentences, config, cache, on_progress,
            cancel_event=cancel_event,
        )

        _report_progress(on_progress, "完成", 100)
        return ProcessResult(
            success=True,
            versions=approved,
            output_files=output_files,
        )
    except Exception as exc:
        logger.exception("Pipeline failed for %s", video_path)
        return ProcessResult(success=False, error=friendly_error(str(exc)))


def friendly_error(raw: str) -> str:
    """Translate common technical errors to user-friendly Chinese messages."""
    low = raw.lower()
    mappings = [
        (["no such file", "filenotfounderror", "文件不存在"],
         "文件不存在或路径无效，请确认文件位置"),
        (["encoder", "codec", "h264_nvenc", "h264_qsv", "h264_amf"],
         "视频编码器不可用，请检查 FFmpeg 安装或切换到 CPU 编码"),
        (["out of memory", "memoryerror", "oom", "cannot allocate"],
         "内存不足，请关闭其他程序后重试，或减少并行处理数"),
        (["timeout", "timed out", "connect", "connectionerror"],
         "网络连接超时，请检查网络后重试"),
        (["auth", "api key", "401", "invalid_api_key", "incorrect api key"],
         "API Key 无效或已过期，请在设置页重新填写"),
        (["无音频", "no audio"],
         "该视频无音频轨道，无法进行语音识别"),
    ]
    for keywords, msg in mappings:
        if any(kw in low for kw in keywords):
            return msg
    return raw


# ---------------------------------------------------------------------------
# SRT subtitle export
# ---------------------------------------------------------------------------


def _format_srt_time(seconds: float) -> str:
    """Format seconds as SRT timestamp: HH:MM:SS,mmm."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def export_srt(sentences: list[Sentence], output_path: Path) -> None:
    """Write ASR sentences as an SRT subtitle file."""
    lines: list[str] = []
    for i, s in enumerate(sentences, 1):
        lines.append(str(i))
        lines.append(f"{_format_srt_time(s.start_sec)} --> {_format_srt_time(s.end_sec)}")
        lines.append(s.text.strip())
        lines.append("")
    output_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("SRT exported: %s (%d entries)", output_path, len(sentences))


# ---------------------------------------------------------------------------
# Stage runners with caching
# ---------------------------------------------------------------------------


def _has_audio_stream(video_path: Path) -> bool:
    """Check if the video file contains an audio stream via ffprobe."""
    import json
    from core.subprocess_utils import run_hidden
    try:
        result = run_hidden(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_streams", "-select_streams", "a", str(video_path)],
            capture_output=True, timeout=15,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout.decode())
            return len(data.get("streams", [])) > 0
    except Exception:
        pass
    return False


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

    # Check for audio stream before running ASR
    if not _has_audio_stream(video_path):
        raise RuntimeError("该视频无音频轨道，无法进行语音识别")

    from core.asr import transcribe_video

    segments = await transcribe_video(
        str(video_path), hotwords=hotwords,
        enable_diarization=config.enable_speaker_diarization,
        engine=getattr(config, "asr_engine", "faster-whisper"),
        model_size=getattr(config, "asr_model_size", "small"),
        on_progress=on_progress,
    )
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
    _report_progress(on_progress, "语音识别完成", 30)
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

    _report_progress(on_progress, "脚本生成完成，解析中...", 50)
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

    _report_progress(on_progress, "质检完成", 65)
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
    cancel_event: threading.Event | None = None,
) -> list[dict]:
    """Run editor (no caching — always regenerate video files)."""
    _report_progress(on_progress, "正在剪辑视频...", 70)

    from core.editor import cut_versions

    output_files = await cut_versions(
        video_path, approved, sentences, config,
        cancel_event=cancel_event,
    )
    logger.info("Editor complete: %d output files", len(output_files))
    _report_progress(on_progress, f"剪辑完成，{len(output_files)} 个文件", 95)
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


async def process_batch(
    video_paths: list[Path],
    config: CutPilotConfig,
    on_progress: Callable[[str, int, int, str], None] | None = None,
    cache: CacheManager | None = None,
    hotwords: str = "",
    max_parallel: int | None = None,
    cancel_event: threading.Event | None = None,
) -> list[ProcessResult]:
    """Process multiple videos with controlled concurrency.

    Args:
        video_paths: List of video file paths to process.
        config: CutPilot configuration.
        on_progress: Optional callback ``(video_name, video_index, percent, stage_label)``.
        cache: Optional cache manager.
        hotwords: Hotwords for ASR.
        max_parallel: Max concurrent video jobs. If None, auto-detected
            from hardware encoder capabilities.
        cancel_event: Optional threading.Event to signal cancellation.

    Returns:
        List of ProcessResult in the same order as video_paths.
    """
    if cache is None:
        cache = CacheManager()

    if max_parallel is None:
        from core.hwaccel import get_max_parallel
        max_parallel = get_max_parallel()

    semaphore = asyncio.Semaphore(max_parallel)
    logger.info("Batch processing %d videos (max_parallel=%d)", len(video_paths), max_parallel)

    async def _process_one(index: int, vpath: Path) -> ProcessResult:
        async with semaphore:
            if cancel_event and cancel_event.is_set():
                return ProcessResult(success=False, error="用户取消处理")

            video_name = vpath.name

            def per_video_progress(label: str, percent: int) -> None:
                if on_progress is not None:
                    on_progress(video_name, index, percent, label)

            return await process_video(
                video_path=vpath,
                config=config,
                on_progress=per_video_progress,
                cache=cache,
                hotwords=hotwords,
                cancel_event=cancel_event,
            )

    tasks = [_process_one(i, p) for i, p in enumerate(video_paths)]
    results = await asyncio.gather(*tasks)
    return list(results)


def build_batch_summary(
    paths: list[Path], results: list[ProcessResult],
) -> dict:
    """Build a summary of batch processing results.

    Returns:
        {"total": int, "success_count": int, "fail_count": int,
         "errors": [{"video": str, "error": str}, ...]}
    """
    errors: list[dict[str, str]] = []
    success_count = 0
    for i, result in enumerate(results):
        if result.success:
            success_count += 1
        else:
            video_name = paths[i].name if i < len(paths) else f"video_{i}"
            errors.append({"video": video_name, "error": result.error})
    return {
        "total": len(results),
        "success_count": success_count,
        "fail_count": len(results) - success_count,
        "errors": errors,
    }


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
