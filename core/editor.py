"""Video cutting engine for CutPilot.

Uses MoviePy for in-memory subclip + concatenation (no intermediate files).
Optional 1.25x speed variant via FFmpeg post-processing.

Extracted and simplified from VideoFactory3 ffmpeg_cutter.py.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from moviepy import VideoFileClip, concatenate_videoclips
from pydantic import BaseModel

from core.config import CutPilotConfig, QUALITY_PRESETS
from core.hwaccel import get_encoder_info, get_ffmpeg_params
from core.models import ExportOptions, Sentence, ScriptVersion
from core.overlay import burn_hook_overlay

logger = logging.getLogger(__name__)


class CutResult(BaseModel):
    """Immutable result of a rough cut operation."""

    model_config = {"frozen": True}

    output_path: str
    duration: float
    width: int
    height: int
    success: bool
    error: str | None = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def cut_versions(
    video_path: Path,
    versions: list[ScriptVersion],
    sentences: list[Sentence],
    config: CutPilotConfig,
    export_options: list[ExportOptions] | None = None,
) -> list[dict]:
    """Cut selected versions from source video.

    For each version, respects export options (if provided) to decide:
    - Whether to produce normal and/or fast speed variants
    - Whether to apply hook overlay
    - Which video quality preset to use

    If export_options is None, falls back to config defaults (all versions,
    normal + fast if generate_fast, hook if enabled, standard quality).

    Returns:
        list of {"version_id": int, "path": str, "speed": str, "quality": str}
    """
    sentence_map: dict[int, Sentence] = {s.id: s for s in sentences}
    output_dir = Path(config.output_dir) if config.output_dir else video_path.parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = video_path.stem

    # Build options lookup — default if not provided
    opts_map: dict[int, ExportOptions] = {}
    if export_options:
        opts_map = {o.version_id: o for o in export_options}

    results: list[dict] = []
    for version in versions:
        opts = opts_map.get(version.version_id)
        if opts is None:
            # Default: export normal, fast if config says so, hook if config says so
            opts = ExportOptions(
                version_id=version.version_id,
                export_normal=True,
                export_fast=config.generate_fast,
                enable_hook=config.enable_hook_overlay,
                video_quality=config.video_quality,
            )

        if not opts.export_normal and not opts.export_fast:
            continue

        time_spans = _resolve_time_spans(version.sentence_ids, sentence_map)
        if not time_spans:
            logger.warning("Version %d: no valid time spans, skipping", version.version_id)
            continue

        quality = opts.video_quality

        # Normal speed
        if opts.export_normal:
            normal_path = str(output_dir / f"{stem}_v{version.version_id}.mp4")
            cut = await rough_cut(str(video_path), time_spans, normal_path, quality)
            if cut.success:
                final_normal = normal_path
                if opts.enable_hook and version.cover_title.strip():
                    final_normal = await _maybe_apply_overlay(
                        normal_path, version.cover_title, config,
                    )
                results.append({
                    "version_id": version.version_id,
                    "path": final_normal,
                    "speed": "normal",
                    "quality": quality,
                })
            else:
                logger.error("Version %d cut failed: %s", version.version_id, cut.error)
                continue

        # 1.25x speed
        if opts.export_fast:
            source_for_fast = normal_path if opts.export_normal else None
            if source_for_fast is None:
                # Need to cut normal first as source for speed-up
                normal_path = str(output_dir / f"{stem}_v{version.version_id}_tmp.mp4")
                cut = await rough_cut(str(video_path), time_spans, normal_path, quality)
                if not cut.success:
                    logger.error("Version %d cut failed: %s", version.version_id, cut.error)
                    continue
                source_for_fast = normal_path

            fast_path = str(output_dir / f"{stem}_v{version.version_id}_fast.mp4")
            try:
                await _run_ffmpeg(
                    "-y", "-i", source_for_fast,
                    "-filter_complex",
                    "[0:v]setpts=0.8*PTS[v];[0:a]atempo=1.25[a]",
                    "-map", "[v]", "-map", "[a]",
                    fast_path,
                )
                final_fast = fast_path
                if opts.enable_hook and version.cover_title.strip():
                    final_fast = await _maybe_apply_overlay(
                        fast_path, version.cover_title, config,
                    )
                results.append({
                    "version_id": version.version_id,
                    "path": final_fast,
                    "speed": "fast",
                    "quality": quality,
                })
            except RuntimeError as exc:
                logger.error("Version %d fast variant failed: %s", version.version_id, exc)

    return results


async def rough_cut(
    source_path: str,
    time_spans: list[tuple[float, float]],
    output_path: str,
    quality: str = "standard",
) -> CutResult:
    """Execute rough cut using MoviePy in-memory concatenation.

    Args:
        source_path: Path to the source video file.
        time_spans: List of (start_sec, end_sec) tuples defining clips.
        output_path: Where to write the final MP4.

    Returns:
        CutResult with output metadata.
    """
    if not time_spans:
        return CutResult(
            output_path=output_path, duration=0.0, width=0, height=0,
            success=False, error="No time spans provided",
        )

    try:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        await asyncio.to_thread(
            _moviepy_cut_and_concat, source_path, time_spans, output_path, quality,
        )

        probe = await _validate_output(output_path)
        return CutResult(
            output_path=output_path,
            duration=probe["duration"],
            width=probe["width"],
            height=probe["height"],
            success=True,
        )
    except Exception as exc:
        logger.exception("Rough cut failed for %s", source_path)
        return CutResult(
            output_path=output_path, duration=0.0, width=0, height=0,
            success=False, error=str(exc),
        )


# ---------------------------------------------------------------------------
# MoviePy cutting (synchronous, called via asyncio.to_thread)
# ---------------------------------------------------------------------------


# Map config quality names to hwaccel quality tiers
_QUALITY_TIER: dict[str, str] = {"draft": "low", "standard": "medium", "high": "high"}


def _moviepy_cut_and_concat(
    source_path: str,
    time_spans: list[tuple[float, float]],
    output_path: str,
    quality: str = "standard",
) -> None:
    """Load source once, subclip each span, concatenate, write output.

    Uses hardware-accelerated encoder when available.
    """
    encoder = get_encoder_info()
    tier = _QUALITY_TIER.get(quality, "medium")
    ffmpeg_params = get_ffmpeg_params(tier)
    # get_ffmpeg_params returns ["-c:v", codec, ...quality_params..., ...extra_params...]
    # MoviePy's write_videofile takes codec separately, so we extract it
    codec = encoder.codec
    # Build remaining params (skip the -c:v and codec from the list)
    extra = [p for i, p in enumerate(ffmpeg_params) if i >= 2]
    extra.extend(["-pix_fmt", "yuv420p"])

    video = VideoFileClip(source_path)
    try:
        clips = []
        for start, end in time_spans:
            clamped_start = max(0, start)
            clamped_end = min(video.duration, end)
            if clamped_end <= clamped_start:
                continue
            clips.append(video.subclipped(clamped_start, clamped_end))

        if not clips:
            raise ValueError("All time spans were out of range")

        final = concatenate_videoclips(clips)
        try:
            final.write_videofile(
                output_path,
                fps=video.fps or 30,
                codec=codec,
                audio_codec="aac",
                ffmpeg_params=extra,
                logger=None,
            )
        finally:
            final.close()
    finally:
        video.close()

    logger.info("Cut+concat (%s): %d clips -> %s", encoder.name, len(time_spans), output_path)


# ---------------------------------------------------------------------------
# FFmpeg / ffprobe helpers
# ---------------------------------------------------------------------------


async def _validate_output(path: str) -> dict[str, Any]:
    """Use ffprobe to validate output: duration, resolution, has audio stream."""
    if not Path(path).exists():
        raise FileNotFoundError(f"Output file not found: {path}")

    process = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        error_msg = stderr.decode().strip() if stderr else "Unknown error"
        raise RuntimeError(f"ffprobe failed for {path}: {error_msg}")

    probe_data = json.loads(stdout.decode())
    streams = probe_data.get("streams", [])
    format_info = probe_data.get("format", {})
    video_stream = _find_stream(streams, "video")
    audio_stream = _find_stream(streams, "audio")

    return {
        "duration": float(format_info.get("duration", 0.0)),
        "width": int(video_stream.get("width", 0)) if video_stream else 0,
        "height": int(video_stream.get("height", 0)) if video_stream else 0,
        "has_audio": audio_stream is not None,
    }


async def _run_ffmpeg(*args: str) -> None:
    """Run ffmpeg with the given arguments and raise on failure."""
    cmd = ["ffmpeg", *args]
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    if process.returncode != 0:
        error_msg = stderr.decode().strip() if stderr else "Unknown error"
        raise RuntimeError(f"ffmpeg failed: {error_msg}")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _maybe_apply_overlay(
    video_path_str: str,
    cover_title: str,
    config: CutPilotConfig,
) -> str:
    """Apply hook overlay if enabled and cover_title is non-empty.

    Returns the (possibly updated) output path as a string.
    """
    if not config.enable_hook_overlay or not cover_title.strip():
        return video_path_str
    result = await burn_hook_overlay(
        Path(video_path_str),
        cover_title,
        duration=config.hook_duration,
    )
    return str(result)


def _resolve_time_spans(
    sentence_ids: list[int],
    sentence_map: dict[int, Sentence],
) -> list[tuple[float, float]]:
    """Map sentence IDs to (start_sec, end_sec) tuples."""
    spans: list[tuple[float, float]] = []
    for sid in sentence_ids:
        sentence = sentence_map.get(sid)
        if sentence is None:
            logger.warning("Sentence id=%d not found, skipping", sid)
            continue
        spans.append((sentence.start_sec, sentence.end_sec))
    return spans


def _find_stream(
    streams: list[dict[str, Any]], codec_type: str,
) -> dict[str, Any] | None:
    """Find the first stream matching the given codec type."""
    for stream in streams:
        if stream.get("codec_type") == codec_type:
            return stream
    return None


def _with_suffix(base_path: str, tag: str) -> str:
    """Create a sibling path with *tag* inserted before the extension."""
    p = Path(base_path)
    return str(p.with_name(f"{p.stem}{tag}{p.suffix}"))


def _escape_filtergraph_path(path: str) -> str:
    """Escape a file path for use inside an ffmpeg filtergraph expression."""
    result = path
    for ch in ("\\", "'", ":", ";", "[", "]"):
        result = result.replace(ch, f"\\{ch}")
    return result
