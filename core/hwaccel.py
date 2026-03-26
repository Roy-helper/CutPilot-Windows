"""Hardware-accelerated video encoder detection for FFmpeg.

Probes the system for the best available H.264 encoder and provides
FFmpeg parameter lists tailored to the detected encoder.

Detection priority (best to worst):
1. macOS VideoToolbox  (h264_videotoolbox)
2. NVIDIA NVENC        (h264_nvenc)
3. Intel QuickSync     (h264_qsv)
4. AMD AMF             (h264_amf)
5. Software fallback   (libx264)
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


class EncoderInfo(BaseModel):
    """Immutable description of a detected video encoder."""

    model_config = {"frozen": True}

    codec: str
    name: str
    is_hardware: bool
    extra_params: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Encoder catalogue (ordered by priority)
# ---------------------------------------------------------------------------

_ENCODER_CANDIDATES: list[dict[str, object]] = [
    {
        "codec": "h264_videotoolbox",
        "name": "Apple VideoToolbox",
        "is_hardware": True,
        "extra_params": ["-allow_sw", "1", "-prio_speed", "0"],
        "grep": "videotoolbox",
        "platform": "darwin",
    },
    {
        "codec": "h264_nvenc",
        "name": "NVIDIA NVENC",
        "is_hardware": True,
        "extra_params": ["-rc", "vbr", "-preset", "p4"],
        "grep": "nvenc",
        "platform": None,
    },
    {
        "codec": "h264_qsv",
        "name": "Intel QuickSync",
        "is_hardware": True,
        "extra_params": ["-preset", "medium"],
        "grep": "qsv",
        "platform": None,
    },
    {
        "codec": "h264_amf",
        "name": "AMD AMF",
        "is_hardware": True,
        "extra_params": ["-quality", "balanced"],
        "grep": "amf",
        "platform": None,
    },
]

_SOFTWARE_ENCODER = EncoderInfo(
    codec="libx264",
    name="Software x264",
    is_hardware=False,
    extra_params=["-preset", "medium"],
)

# Module-level cache (None = not yet detected)
_cached_encoder: EncoderInfo | None = None

# ---------------------------------------------------------------------------
# Quality presets — CRF / quality values per tier
# ---------------------------------------------------------------------------

_QUALITY_CRF: dict[str, int] = {
    "low": 28,
    "medium": 23,
    "high": 18,
}

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _ffmpeg_has_encoder(grep_token: str) -> bool:
    """Return True if ``ffmpeg -encoders`` output contains *grep_token*."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-encoders"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return grep_token in result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        logger.debug("ffmpeg probe failed for '%s': %s", grep_token, exc)
        return False


def _pick_encoder() -> EncoderInfo:
    """Walk the candidate list and return the first encoder available."""
    for candidate in _ENCODER_CANDIDATES:
        # Skip platform-restricted encoders on other platforms
        required_platform = candidate["platform"]
        if required_platform is not None and sys.platform != required_platform:
            continue

        grep_token: str = candidate["grep"]  # type: ignore[assignment]
        if _ffmpeg_has_encoder(grep_token):
            encoder = EncoderInfo(
                codec=str(candidate["codec"]),
                name=str(candidate["name"]),
                is_hardware=bool(candidate["is_hardware"]),
                extra_params=list(candidate["extra_params"]),  # type: ignore[arg-type]
            )
            logger.info("Detected hardware encoder: %s (%s)", encoder.name, encoder.codec)
            return encoder

    logger.info("No hardware encoder found, using software fallback (libx264)")
    return _SOFTWARE_ENCODER


# ---------------------------------------------------------------------------
# Quality-parameter mapping per encoder family
# ---------------------------------------------------------------------------


def _quality_params_for(encoder: EncoderInfo, crf: int) -> list[str]:
    """Return encoder-specific quality flags for the given CRF value."""
    codec = encoder.codec

    if codec == "h264_videotoolbox":
        # VideoToolbox uses -q:v (1-100, lower = higher quality).
        # Map CRF 18-28 roughly to q:v 40-65.
        q_value = max(30, min(70, 35 + crf))
        return ["-q:v", str(q_value)]

    if codec == "h264_nvenc":
        # NVENC: -cq maps closely to CRF semantics.
        return ["-cq", str(crf), "-b:v", "0"]

    if codec == "h264_qsv":
        return ["-global_quality", str(crf)]

    if codec == "h264_amf":
        # AMF uses -qp_i / -qp_p for constant-QP mode.
        return ["-rc", "cqp", "-qp_i", str(crf), "-qp_p", str(crf)]

    # Software (libx264)
    return ["-crf", str(crf)]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_best_encoder() -> EncoderInfo:
    """Detect the best available encoder, cache and return it.

    Safe to call multiple times — detection runs only once.
    """
    global _cached_encoder  # noqa: PLW0603
    if _cached_encoder is not None:
        return _cached_encoder

    try:
        _cached_encoder = _pick_encoder()
    except Exception:
        logger.exception("Encoder detection failed, falling back to libx264")
        _cached_encoder = _SOFTWARE_ENCODER

    return _cached_encoder


def get_encoder_info() -> EncoderInfo:
    """Return the cached encoder without re-detecting.

    If detection has not run yet, triggers detection automatically.
    """
    if _cached_encoder is not None:
        return _cached_encoder
    return detect_best_encoder()


def get_ffmpeg_params(quality: str = "medium") -> list[str]:
    """Build a full FFmpeg encoder parameter list for *quality*.

    Args:
        quality: One of ``"low"``, ``"medium"``, ``"high"``.

    Returns:
        A list of CLI tokens, e.g.
        ``["-c:v", "h264_videotoolbox", "-q:v", "53", ...]``.

    Raises:
        ValueError: If *quality* is not a recognised preset.
    """
    if quality not in _QUALITY_CRF:
        valid = ", ".join(sorted(_QUALITY_CRF))
        raise ValueError(f"Unknown quality preset '{quality}'. Choose from: {valid}")

    encoder = get_encoder_info()
    crf = _QUALITY_CRF[quality]

    params: list[str] = ["-c:v", encoder.codec]
    params.extend(_quality_params_for(encoder, crf))
    params.extend(encoder.extra_params)
    return params


def get_max_parallel() -> int:
    """Return the recommended number of parallel encode jobs.

    Based on encoder type and actual CPU core count:
    - Hardware encoder (VideoToolbox/NVENC/QSV): limited by encoder channels,
      typically min(cpu_cores, 8) — hardware handles encoding, CPU still does
      ASR + AI calls + MoviePy processing.
    - Software encoder (libx264): CPU-bound, use half the cores to avoid
      overloading during AI API calls.
    """
    cpu_count = os.cpu_count() or 2
    encoder = get_encoder_info()

    if encoder.is_hardware:
        # Hardware encoder: CPU is free for ASR/AI, allow more parallelism
        # but cap at 8 to avoid memory issues with large videos
        return min(cpu_count, 8)

    # Software: heavy CPU usage per encode, be conservative
    return max(1, cpu_count // 2)
