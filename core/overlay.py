"""Hook text overlay for CutPilot videos.

Generates a styled text card PNG and burns it onto the first few seconds
of a video using FFmpeg.
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from core.text_render import find_cjk_font, render_text_card

logger = logging.getLogger(__name__)


def _needs_temp_copy(path: str) -> bool:
    """Check if the path has non-ASCII chars that FFmpeg can't handle on Windows."""
    if sys.platform != "win32":
        return False
    try:
        path.encode("ascii")
        return False
    except UnicodeEncodeError:
        return True


def create_hook_image(
    text: str,
    video_width: int,
    video_height: int,
) -> Path | None:
    """Generate a hook-text PNG overlay sized for the given video.

    Returns the path to a temporary PNG file, or None if CJK font unavailable.
    """
    font_path = find_cjk_font()
    if font_path is None:
        logger.warning("跳过 Hook 文字叠加: 未找到中文字体，请安装 PingFang/微软雅黑等字体")
        return None
    font_size = max(36, int(video_width * 0.08))

    img = render_text_card(
        text,
        video_width,
        font_path,
        font_size,
    )

    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp.close()
    img.save(tmp.name, "PNG")
    logger.debug("Hook image saved: %s (%dx%d)", tmp.name, img.width, img.height)
    return Path(tmp.name)


async def burn_hook_overlay(
    video_path: Path,
    hook_text: str,
    duration: float = 3.0,
) -> Path:
    """Burn a hook-text overlay onto the first *duration* seconds of a video.

    Returns the path to the new video file (``{stem}_hooked.mp4``).
    If anything fails, logs a warning and returns the original path unchanged.
    """
    if not hook_text.strip():
        return video_path

    try:
        probe = _probe_video_dimensions(video_path)
        width, height = probe["width"], probe["height"]

        overlay_png = create_hook_image(hook_text, width, height)
        if overlay_png is None:
            return video_path
        try:
            output_path = video_path.with_name(
                f"{video_path.stem}_hooked{video_path.suffix}"
            )
            _ffmpeg_overlay(video_path, overlay_png, output_path, duration)
            logger.info("Hook overlay burned: %s -> %s", video_path.name, output_path.name)
            return output_path
        finally:
            overlay_png.unlink(missing_ok=True)
    except Exception:
        logger.warning(
            "Hook 文字叠加失败: %s — 将使用无 Hook 版本",
            video_path.name,
            exc_info=True,
        )
        return video_path


# ---------------------------------------------------------------------------
# FFmpeg helpers (subprocess.run — Windows thread-safe)
# ---------------------------------------------------------------------------


def _ffmpeg_overlay(
    video_path: Path,
    overlay_path: Path,
    output_path: Path,
    duration: float,
) -> None:
    """Composite *overlay_path* onto *video_path* for first *duration* seconds."""
    fade_out_start = max(0, duration - 0.5)

    filter_complex = (
        f"[1:v]format=rgba,"
        f"fade=t=out:st={fade_out_start}:d=0.5:alpha=1[ovr];"
        f"[0:v][ovr]overlay=(main_w-overlay_w)/2:main_h*0.15:"
        f"enable='between(t,0,{duration})'[out]"
    )

    from core.editor import _get_fps_mode_flag

    # Protect non-ASCII paths on Windows
    temp_video: str | None = None
    temp_out: str | None = None
    try:
        effective_video = str(video_path)
        if _needs_temp_copy(effective_video):
            fd, temp_video = tempfile.mkstemp(suffix=video_path.suffix)
            import os
            os.close(fd)
            shutil.copy2(effective_video, temp_video)
            effective_video = temp_video

        effective_output = str(output_path)
        if _needs_temp_copy(effective_output):
            cache_dir = Path.home() / ".cutpilot" / "cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            import uuid
            temp_out = str(cache_dir / f"ovl_{uuid.uuid4().hex[:8]}{output_path.suffix}")
            effective_output = temp_out

        cmd = [
            "ffmpeg", "-y",
            "-i", effective_video,
            "-i", str(overlay_path),
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-map", "0:a?",
            *_get_fps_mode_flag(),
            "-c:a", "copy",
            "-c:v", "libx264",
            "-crf", "18",
            "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            effective_output,
        ]

        completed = subprocess.run(cmd, capture_output=True, timeout=300)
        if completed.returncode != 0:
            error_msg = completed.stderr.decode(errors="replace").strip()
            if len(error_msg) > 500:
                error_msg = error_msg[-500:]
            raise RuntimeError(f"FFmpeg overlay failed: {error_msg}")

        # Move temp output to real path if needed
        if temp_out:
            shutil.move(temp_out, str(output_path))
            temp_out = None
    finally:
        if temp_video:
            Path(temp_video).unlink(missing_ok=True)
        if temp_out:
            Path(temp_out).unlink(missing_ok=True)


def _probe_video_dimensions(video_path: Path) -> dict[str, int]:
    """Return {'width': int, 'height': int} for the video."""
    effective_path = str(video_path)
    temp_probe: str | None = None

    try:
        if _needs_temp_copy(effective_path):
            fd, temp_probe = tempfile.mkstemp(suffix=video_path.suffix)
            import os
            os.close(fd)
            shutil.copy2(effective_path, temp_probe)
            effective_path = temp_probe

        completed = subprocess.run(
            ["ffprobe", "-v", "quiet",
             "-print_format", "json",
             "-show_streams",
             "-select_streams", "v:0",
             effective_path],
            capture_output=True, timeout=30,
        )

        if completed.returncode != 0:
            error_msg = completed.stderr.decode(errors="replace").strip() if completed.stderr else "Unknown error"
            raise RuntimeError(f"ffprobe failed: {error_msg}")

        data = json.loads(completed.stdout.decode())
        streams = data.get("streams", [])
        if not streams:
            raise RuntimeError(f"No video stream found in {video_path}")

        stream = streams[0]
        return {
            "width": int(stream["width"]),
            "height": int(stream["height"]),
        }
    finally:
        if temp_probe:
            Path(temp_probe).unlink(missing_ok=True)
