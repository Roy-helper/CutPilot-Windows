"""Hook text overlay for CutPilot videos.

Generates a styled text card PNG and burns it onto the first few seconds
of a video using FFmpeg.
"""
from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

from core.text_render import find_cjk_font, render_text_card

logger = logging.getLogger(__name__)


def create_hook_image(
    text: str,
    video_width: int,
    video_height: int,
) -> Path:
    """Generate a hook-text PNG overlay sized for the given video.

    Returns the path to a temporary PNG file (caller must clean up).
    """
    font_path = find_cjk_font()
    font_size = max(24, int(video_width * 0.05))

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
        probe = await _probe_video_dimensions(video_path)
        width, height = probe["width"], probe["height"]

        overlay_png = create_hook_image(hook_text, width, height)
        try:
            output_path = video_path.with_name(
                f"{video_path.stem}_hooked{video_path.suffix}"
            )
            await _ffmpeg_overlay(video_path, overlay_png, output_path, duration)
            logger.info("Hook overlay burned: %s -> %s", video_path.name, output_path.name)
            return output_path
        finally:
            overlay_png.unlink(missing_ok=True)
    except Exception:
        logger.warning(
            "Hook overlay failed for %s, keeping original",
            video_path.name,
            exc_info=True,
        )
        return video_path


# ---------------------------------------------------------------------------
# FFmpeg helpers
# ---------------------------------------------------------------------------


async def _ffmpeg_overlay(
    video_path: Path,
    overlay_path: Path,
    output_path: Path,
    duration: float,
) -> None:
    """Composite *overlay_path* onto *video_path* with fade in/out."""
    fade_in_dur = 0.3
    fade_out_start = max(0, duration - 0.5)
    fade_out_dur = 0.5

    filter_complex = (
        f"[1:v]format=rgba,"
        f"fade=t=in:st=0:d={fade_in_dur}:alpha=1,"
        f"fade=t=out:st={fade_out_start}:d={fade_out_dur}:alpha=1[ovr];"
        f"[0:v][ovr]overlay=(W-w)/2:H*0.15:"
        f"enable='between(t,0,{duration})'[out]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(overlay_path),
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-map", "0:a?",
        "-c:a", "copy",
        "-c:v", "libx264",
        "-crf", "18",
        "-preset", "ultrafast",
        "-pix_fmt", "yuv420p",
        str(output_path),
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()

    if process.returncode != 0:
        error_msg = stderr.decode().strip() if stderr else "Unknown error"
        raise RuntimeError(f"FFmpeg overlay failed: {error_msg}")


async def _probe_video_dimensions(video_path: Path) -> dict[str, int]:
    """Return {'width': int, 'height': int} for the video."""
    import json

    process = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-select_streams", "v:0",
        str(video_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        error_msg = stderr.decode().strip() if stderr else "Unknown error"
        raise RuntimeError(f"ffprobe failed: {error_msg}")

    data = json.loads(stdout.decode())
    streams = data.get("streams", [])
    if not streams:
        raise RuntimeError(f"No video stream found in {video_path}")

    stream = streams[0]
    return {
        "width": int(stream["width"]),
        "height": int(stream["height"]),
    }
