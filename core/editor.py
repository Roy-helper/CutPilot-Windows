"""Video cutting engine for CutPilot.

Single-pass FFmpeg pipeline: trim + concat + optional speed in one
filter_complex invocation. No intermediate files, no MoviePy dependency,
no cumulative quality loss.

Upgraded from MoviePy to pure FFmpeg, borrowing VF4's filter_complex
approach while keeping CutPilot's time-clamping, quality tiers and
hook-overlay post-processing.
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from core.config import CutPilotConfig
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
    cancel_event: threading.Event | None = None,
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
    base_output = Path(config.output_dir).expanduser() if config.output_dir else video_path.parent / "output"
    stem = video_path.stem
    # Each video gets its own subfolder: output/<video_stem>/
    output_dir = base_output / stem
    output_dir.mkdir(parents=True, exist_ok=True)

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
            cut = await rough_cut(str(video_path), time_spans, normal_path, quality, cancel_event=cancel_event)
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

        # 1.25x speed — single-pass with speed baked into filter_complex
        if opts.export_fast:
            fast_path = str(output_dir / f"{stem}_v{version.version_id}_fast.mp4")
            fast_cut = await rough_cut(
                str(video_path), time_spans, fast_path, quality, speed=1.25,
                cancel_event=cancel_event,
            )
            if fast_cut.success:
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
            else:
                logger.error("Version %d fast variant failed: %s", version.version_id, fast_cut.error)

    return results


async def rough_cut(
    source_path: str,
    time_spans: list[tuple[float, float]],
    output_path: str,
    quality: str = "standard",
    speed: float = 1.0,
    cancel_event: threading.Event | None = None,
) -> CutResult:
    """Single-pass rough cut via FFmpeg filter_complex.

    Builds one filter_complex graph that trims + concatenates all clips
    from the source video in a single encode pass. No intermediate files.

    Args:
        source_path: Path to the source video file.
        time_spans: List of (start_sec, end_sec) tuples defining clips.
        output_path: Where to write the final MP4.
        quality: One of "draft", "standard", "high".
        speed: Playback speed multiplier (1.0 = normal, 1.25 = faster).

    Returns:
        CutResult with output metadata.
    """
    if not time_spans:
        return CutResult(
            output_path=output_path, duration=0.0, width=0, height=0,
            success=False, error="No time spans provided",
        )

    temp_source: str | None = None
    temp_output: str | None = None
    try:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # Chinese filenames on Windows: FFmpeg can't handle non-ASCII paths
        if _needs_temp_copy(source_path):
            suffix = Path(source_path).suffix
            fd, temp_source = tempfile.mkstemp(suffix=suffix)
            import os
            os.close(fd)
            shutil.copy2(source_path, temp_source)
            effective_source = temp_source
        else:
            effective_source = source_path

        # Output path protection: write to temp, then move to real path
        if _needs_temp_copy(output_path):
            cache_dir = Path.home() / ".cutpilot" / "cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            import uuid
            temp_output = str(cache_dir / f"out_{uuid.uuid4().hex[:8]}{Path(output_path).suffix}")
            effective_output = temp_output
        else:
            effective_output = output_path

        # Probe source duration for time clamping
        source_duration = _probe_duration(effective_source)

        # Build filter_complex: trim each span → concat → optional speed
        filter_parts: list[str] = []
        concat_v: list[str] = []
        concat_a: list[str] = []

        for i, (start, end) in enumerate(time_spans):
            # Clamp to source boundaries (CutPilot safety)
            clamped_start = max(0.0, start)
            clamped_end = min(source_duration, end) if source_duration > 0 else end
            if clamped_end <= clamped_start:
                continue
            filter_parts.append(
                f"[0:v]trim=start={clamped_start:.3f}:end={clamped_end:.3f},"
                f"setpts=PTS-STARTPTS[v{i}]"
            )
            filter_parts.append(
                f"[0:a]atrim=start={clamped_start:.3f}:end={clamped_end:.3f},"
                f"asetpts=PTS-STARTPTS,aresample=async=1[a{i}]"
            )
            concat_v.append(f"[v{i}]")
            concat_a.append(f"[a{i}]")

        if not concat_v:
            return CutResult(
                output_path=output_path, duration=0.0, width=0, height=0,
                success=False, error="All time spans were out of range",
            )

        n = len(concat_v)
        concat_inputs = "".join(f"{concat_v[i]}{concat_a[i]}" for i in range(n))
        filter_parts.append(
            f"{concat_inputs}concat=n={n}:v=1:a=1[outv][outa]"
        )

        # Apply speed change if not 1.0x
        if speed != 1.0 and speed > 0:
            pts_factor = 1.0 / speed
            filter_parts.append(f"[outv]setpts={pts_factor:.4f}*PTS[finalv]")
            filter_parts.append(f"[outa]atempo={speed:.4f}[spda]")
            audio_label = "[spda]"
            map_v = "[finalv]"
        else:
            audio_label = "[outa]"
            map_v = "[outv]"

        # Audio normalization: loudnorm to -14 LUFS (Douyin standard)
        filter_parts.append(
            f"{audio_label}loudnorm=I=-14:TP=-1:LRA=11[norma]"
        )
        map_a = "[norma]"

        filter_complex = ";\n".join(filter_parts)

        # Encoder params from hwaccel quality tiers
        tier = _QUALITY_TIER.get(quality, "medium")
        enc_params = get_ffmpeg_params(tier)

        cmd: list[str] = [
            "ffmpeg", "-y", "-i", effective_source,
            "-filter_complex", filter_complex,
            "-map", map_v, "-map", map_a,
            *_get_fps_mode_flag(),
            *enc_params,
            "-c:a", "aac", "-b:a", "128k",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            effective_output,
        ]

        _run_ffmpeg_cmd(cmd, cancel_event=cancel_event)

        # Move temp output to real path if needed
        if temp_output:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            shutil.move(temp_output, output_path)
            temp_output = None  # moved successfully, don't clean up

        probe = _validate_output(output_path)

        speed_label = f" @{speed}x" if speed != 1.0 else ""
        encoder = get_encoder_info()
        logger.info(
            "FFmpeg single-pass%s: %d clips -> %s [%s]",
            speed_label, len(time_spans), output_path, encoder.name,
        )

        return CutResult(
            output_path=output_path,
            duration=probe["duration"],
            width=probe["width"],
            height=probe["height"],
            success=True,
        )
    except Exception as exc:
        logger.exception("Rough cut failed for %s", source_path)
        # Clean up incomplete output file
        Path(output_path).unlink(missing_ok=True)
        return CutResult(
            output_path=output_path, duration=0.0, width=0, height=0,
            success=False, error=str(exc),
        )
    finally:
        if temp_source:
            Path(temp_source).unlink(missing_ok=True)
        if temp_output:
            Path(temp_output).unlink(missing_ok=True)


# Map config quality names to hwaccel quality tiers
_QUALITY_TIER: dict[str, str] = {"draft": "low", "standard": "medium", "high": "high"}

# Cache for FFmpeg version check
_cached_fps_mode_flag: list[str] | None = None


# ---------------------------------------------------------------------------
# FFmpeg / ffprobe helpers (subprocess.run — Windows thread-safe)
# ---------------------------------------------------------------------------


def _get_fps_mode_flag() -> list[str]:
    """Return the correct CFR flag for the installed FFmpeg version.

    FFmpeg ≥5.1 uses ``-fps_mode cfr``, older versions use ``-vsync cfr``.
    """
    global _cached_fps_mode_flag  # noqa: PLW0603
    if _cached_fps_mode_flag is not None:
        return list(_cached_fps_mode_flag)
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True, text=True, timeout=5,
        )
        # Parse "ffmpeg version N.N..." from first line
        first_line = result.stdout.split("\n")[0]
        # e.g. "ffmpeg version 6.1.2 Copyright ..."
        parts = first_line.split()
        for part in parts:
            if part[0].isdigit():
                major, minor = part.split(".")[:2]
                if int(major) > 5 or (int(major) == 5 and int(minor) >= 1):
                    _cached_fps_mode_flag = ["-fps_mode", "cfr"]
                else:
                    _cached_fps_mode_flag = ["-vsync", "cfr"]
                return list(_cached_fps_mode_flag)
    except Exception:
        pass
    _cached_fps_mode_flag = ["-vsync", "cfr"]
    return list(_cached_fps_mode_flag)


def _run_ffmpeg_cmd(
    cmd: list[str],
    cancel_event: threading.Event | None = None,
) -> None:
    """Run an ffmpeg command and raise on failure.

    If *cancel_event* is provided, polls the process every 0.5s and kills it
    when cancellation is requested. Otherwise blocks with a 600s timeout.
    """
    if cancel_event is None:
        # Simple blocking path (backward-compatible)
        completed = subprocess.run(cmd, capture_output=True, timeout=600)
        if completed.returncode != 0:
            error_msg = completed.stderr.decode(errors="replace").strip()
            if len(error_msg) > 500:
                error_msg = error_msg[-500:]
            raise RuntimeError(f"ffmpeg failed (exit {completed.returncode}): {error_msg}")
        return

    # Cancellable path: Popen + poll loop
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        while process.poll() is None:
            if cancel_event.is_set():
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                raise RuntimeError("用户取消处理")
            try:
                process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                continue

        stderr = process.stderr.read() if process.stderr else b""
        if process.returncode != 0:
            error_msg = stderr.decode(errors="replace").strip()
            if len(error_msg) > 500:
                error_msg = error_msg[-500:]
            raise RuntimeError(f"ffmpeg failed (exit {process.returncode}): {error_msg}")
    except RuntimeError:
        raise
    except Exception:
        process.kill()
        process.wait()
        raise


def _validate_output(path: str) -> dict[str, Any]:
    """Use ffprobe to validate output: duration, resolution, has audio stream."""
    if not Path(path).exists():
        raise FileNotFoundError(f"Output file not found: {path}")

    completed = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_format", "-show_streams", path],
        capture_output=True, timeout=30,
    )

    if completed.returncode != 0:
        error_msg = completed.stderr.decode(errors="replace").strip() if completed.stderr else "Unknown error"
        raise RuntimeError(f"ffprobe failed for {path}: {error_msg}")

    probe_data = json.loads(completed.stdout.decode())
    streams = probe_data.get("streams", [])
    format_info = probe_data.get("format", {})
    video_stream = _find_stream(streams, "video")
    audio_stream = _find_stream(streams, "audio")

    # VFR detection: compare r_frame_rate vs avg_frame_rate
    is_vfr = False
    if video_stream:
        is_vfr = _detect_vfr(video_stream, path)

    return {
        "duration": float(format_info.get("duration", 0.0)),
        "width": int(video_stream.get("width", 0)) if video_stream else 0,
        "height": int(video_stream.get("height", 0)) if video_stream else 0,
        "has_audio": audio_stream is not None,
        "is_vfr": is_vfr,
    }


def _probe_duration(path: str) -> float:
    """Quick ffprobe to get source video duration in seconds."""
    try:
        completed = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", path],
            capture_output=True, timeout=15,
        )
        if completed.returncode == 0:
            data = json.loads(completed.stdout.decode())
            return float(data.get("format", {}).get("duration", 0.0))
    except Exception:
        pass
    return 0.0


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


def _parse_frame_rate(rate_str: str) -> float:
    """Parse ffprobe frame rate string like '30000/1001' or '30' to float."""
    if "/" in rate_str:
        num, den = rate_str.split("/", 1)
        den_f = float(den)
        return float(num) / den_f if den_f > 0 else 0.0
    return float(rate_str) if rate_str else 0.0


def _detect_vfr(video_stream: dict[str, Any], path: str) -> bool:
    """Check if a video stream is variable frame rate (VFR).

    Compares r_frame_rate and avg_frame_rate; if they differ by more than
    5%, the video is likely VFR (common with phone recordings).
    """
    try:
        r_rate = _parse_frame_rate(video_stream.get("r_frame_rate", "0"))
        avg_rate = _parse_frame_rate(video_stream.get("avg_frame_rate", "0"))
        if r_rate > 0 and avg_rate > 0:
            ratio = r_rate / avg_rate
            if ratio > 1.05 or ratio < 0.95:
                logger.warning(
                    "VFR detected in %s: r_frame_rate=%.2f, avg_frame_rate=%.2f",
                    path, r_rate, avg_rate,
                )
                return True
    except (ValueError, ZeroDivisionError):
        pass
    return False


def _needs_temp_copy(path: str) -> bool:
    """Check if the path has non-ASCII chars that FFmpeg can't handle on Windows."""
    if sys.platform != "win32":
        return False
    try:
        path.encode("ascii")
        return False
    except UnicodeEncodeError:
        return True


def _find_stream(
    streams: list[dict[str, Any]], codec_type: str,
) -> dict[str, Any] | None:
    """Find the first stream matching the given codec type."""
    for stream in streams:
        if stream.get("codec_type") == codec_type:
            return stream
    return None


