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


def diagnose_gpu() -> dict:
    """Return a diagnostic snapshot of the current GPU/encoder state.

    Used by the frontend to display encoder info with GPU model.
    """
    encoder = get_encoder_info()
    is_nvenc = encoder.codec == "h264_nvenc"
    return {
        "encoder_name": encoder.name,
        "encoder_codec": encoder.codec,
        "is_hardware": encoder.is_hardware,
        "detection_method": "ffmpeg -encoders probe",
        "gpu_model": _get_gpu_name() if is_nvenc else None,
        "nvenc_sessions": _get_nvenc_max_sessions() if is_nvenc else None,
    }


_cached_parallel: int | None = None


def _get_available_ram_gb() -> float:
    """Return available system RAM in GB."""
    try:
        import psutil
        return psutil.virtual_memory().available / (1024 ** 3)
    except ImportError:
        pass
    # Fallback: read from OS
    try:
        if sys.platform == "darwin":
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True, text=True, timeout=5,
            )
            total_bytes = int(result.stdout.strip())
            return total_bytes / (1024 ** 3) * 0.6  # assume 60% available
        elif sys.platform == "win32":
            result = subprocess.run(
                ["wmic", "OS", "get", "FreePhysicalMemory"],
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.strip().splitlines():
                line = line.strip()
                if line.isdigit():
                    return int(line) / (1024 ** 2)  # KB to GB
    except Exception:
        pass
    return 4.0  # conservative fallback


def _get_gpu_name() -> str | None:
    """Query GPU model name via nvidia-smi. Returns None if unavailable."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().splitlines()[0]
    except (FileNotFoundError, OSError, IndexError):
        pass
    return None


def _get_nvenc_max_sessions() -> int:
    """Query GPU model via nvidia-smi and return NVENC concurrent session limit.

    Consumer GPUs (GeForce): 3 sessions (driver-enforced).
    Professional GPUs (Quadro, A-series, RTX A-series): unlimited, cap at 8.
    """
    gpu_name = _get_gpu_name()
    if gpu_name is None:
        return 3  # conservative default

    gpu_upper = gpu_name.upper()
    logger.info("Detected GPU: %s", gpu_name)

    # Professional / datacenter cards have no NVENC session limit
    pro_keywords = ["QUADRO", "TESLA", "RTX A", "RTX 4000", "RTX 5000",
                    "RTX 6000", "RTX 8000", "A100", "A40", "A30", "A10",
                    "L40", "L4", "H100", "H200"]
    if any(kw in gpu_upper for kw in pro_keywords):
        return 8  # effectively unlimited, cap for sanity
    return 3  # GeForce consumer limit


def benchmark_parallel() -> dict:
    """Run a quick benchmark to determine safe parallel job count.

    Tests actual system capacity by checking:
    1. CPU core count
    2. Available RAM (each video job needs ~0.8GB with faster-whisper)
    3. Encoder type (hardware vs software)
    4. GPU NVENC session limit (for NVIDIA hardware encoders)

    Returns:
        {"max_parallel": int, "cpu_cores": int, "ram_gb": float,
         "encoder": str, "reason": str}
    """
    global _cached_parallel  # noqa: PLW0603
    cpu_count = os.cpu_count() or 2
    ram_gb = _get_available_ram_gb()
    encoder = get_encoder_info()

    # Each video processing job uses approximately:
    # - faster-whisper ASR: ~0.3GB RAM
    # - FFmpeg encode: ~0.5GB RAM
    # - Total per job: ~0.8GB
    ram_per_job_gb = 0.8
    max_by_ram = max(1, int(ram_gb / ram_per_job_gb))

    if encoder.is_hardware:
        # Hardware encoder: CPU available for other work
        max_by_cpu = cpu_count
        # Check GPU-specific NVENC session limit
        if encoder.codec == "h264_nvenc":
            max_by_gpu = _get_nvenc_max_sessions()
        else:
            max_by_gpu = 4  # VideoToolbox / QSV / AMF conservative default
    else:
        # Software encoder: each encode uses ~2 CPU cores
        max_by_cpu = max(1, cpu_count // 2)
        max_by_gpu = 999  # no GPU constraint

    # Take the minimum of all constraints
    recommended = min(max_by_ram, max_by_cpu, max_by_gpu, 8)  # absolute cap at 8
    recommended = max(1, recommended)  # at least 1

    reason_parts = []
    bottleneck = min(max_by_ram, max_by_cpu, max_by_gpu)
    if bottleneck == max_by_gpu and encoder.is_hardware:
        reason_parts.append(f"GPU 编码限制 (最多 {max_by_gpu} 路)")
    if bottleneck == max_by_ram:
        reason_parts.append(f"内存限制 ({ram_gb:.1f}GB 可用)")
    if bottleneck == max_by_cpu:
        reason_parts.append(f"CPU 限制 ({cpu_count} 核)")
    reason = "、".join(reason_parts) if reason_parts else f"{cpu_count} 核 CPU, {ram_gb:.1f}GB 内存"

    _cached_parallel = recommended
    logger.info(
        "Benchmark: cpu=%d, ram=%.1fGB, encoder=%s, gpu_limit=%s → parallel=%d (%s)",
        cpu_count, ram_gb, encoder.name,
        max_by_gpu if encoder.is_hardware else "N/A",
        recommended, reason,
    )

    return {
        "max_parallel": recommended,
        "cpu_cores": cpu_count,
        "ram_gb": round(ram_gb, 1),
        "encoder": encoder.name,
        "is_hardware": encoder.is_hardware,
        "reason": reason,
    }


def get_max_parallel() -> int:
    """Return recommended parallel count. Uses cached benchmark result."""
    if _cached_parallel is not None:
        return _cached_parallel
    result = benchmark_parallel()
    return result["max_parallel"]
