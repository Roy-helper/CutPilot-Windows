"""FunASR integration for speech-to-text transcription.

CutPilot: Direct local model call, auto-detects GPU/CPU.
Falls back to HTTP API if local model unavailable.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Lazy-loaded local model singleton (thread-safe)
_local_model = None
_model_load_attempted = False
_model_lock = threading.Lock()


class TranscriptSegment(BaseModel):
    """Immutable transcript segment with timing information."""

    model_config = {"frozen": True}

    start: float
    end: float
    text: str
    speaker: str | None = None


def check_asr_available() -> dict:
    """Check ASR engine availability.

    Returns:
        {"installed": bool, "models_cached": bool, "engine": str, "message": str}
    """
    # Check Whisper (primary engine, lightweight)
    try:
        import whisper  # noqa: F401
        # Check if small model is cached
        cache_dir = Path.home() / ".cache" / "whisper"
        has_whisper_model = (cache_dir / "small.pt").exists() if cache_dir.exists() else False
        if has_whisper_model:
            return {"installed": True, "models_cached": True, "engine": "whisper",
                    "message": "语音识别就绪 (Whisper)"}
        else:
            return {"installed": True, "models_cached": False, "engine": "whisper",
                    "message": "首次使用需下载语音模型（约 461MB），处理时自动下载"}
    except ImportError:
        pass

    # Check FunASR (optional, better quality)
    try:
        import funasr  # noqa: F401
        return {"installed": True, "models_cached": False, "engine": "funasr",
                "message": "语音识别就绪 (FunASR)"}
    except ImportError:
        pass

    return {"installed": False, "models_cached": False, "engine": "none",
            "message": "语音识别组件未安装"}


def _get_local_model():
    """Lazy-load FunASR model (singleton, thread-safe). Returns None if unavailable.

    First run: allows model download from ModelScope (disable_update=False).
    Subsequent runs: uses cached model (disable_update=True).
    """
    global _local_model, _model_load_attempted
    with _model_lock:
        if _model_load_attempted:
            return _local_model
        _model_load_attempted = True
        try:
            from funasr import AutoModel
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"

            # Check if models are already cached
            status = check_asr_available()
            disable_update = status["models_cached"]
            if not disable_update:
                logger.info("首次运行，正在下载语音识别模型（约 1GB）...")

            logger.info("Loading FunASR (device=%s, cached=%s)...", device, disable_update)
            try:
                _local_model = AutoModel(
                    model="iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
                    vad_model="fsmn-vad",
                    punc_model="ct-punc",
                    spk_model="cam++",
                    device=device,
                    disable_update=disable_update,
                )
                logger.info("FunASR SeACo-Paraformer loaded successfully")
            except Exception as spk_exc:
                logger.warning("SeACo-Paraformer failed, trying paraformer-zh: %s", spk_exc)
                _local_model = AutoModel(
                    model="paraformer-zh",
                    vad_model="fsmn-vad",
                    punc_model="ct-punc",
                    device=device,
                    disable_update=disable_update,
                )
                logger.info("FunASR paraformer-zh loaded successfully")
        except Exception as exc:
            logger.warning("FunASR unavailable: %s", exc)
            _local_model = None
        return _local_model


def _transcribe_local(
    video_path: str,
    hotwords: str = "",
    enable_diarization: bool = True,
) -> list[TranscriptSegment]:
    """Transcribe using local FunASR model (VF1 mode — fast)."""
    model = _get_local_model()
    if model is None:
        raise RuntimeError("语音识别模型未安装，请运行: pip install funasr torch")

    if hotwords:
        try:
            res = model.generate(
                input=video_path, batch_size_s=60, use_itn=True, hotword=hotwords,
            )
        except TypeError:
            logger.warning("FunASR version does not support hotword, falling back")
            res = model.generate(input=video_path, batch_size_s=60, use_itn=True)
    else:
        res = model.generate(input=video_path, batch_size_s=60, use_itn=True)
    result_data = res[0]

    segments: list[TranscriptSegment] = []

    # Priority 1: sentence_info (sentence-level timestamps)
    sentence_info = result_data.get("sentence_info")
    if sentence_info:
        for item in sentence_info:
            spk_raw = item.get("spk", None)
            speaker = str(spk_raw) if spk_raw is not None else None
            segments.append(TranscriptSegment(
                start=item["start"] / 1000.0,
                end=item["end"] / 1000.0,
                text=item["text"].strip(),
                speaker=speaker,
            ))
        if not enable_diarization:
            segments = [TranscriptSegment(start=s.start, end=s.end, text=s.text, speaker=None) for s in segments]
        return segments

    # Priority 2: word-level timestamps → split by punctuation
    # timestamps are 1:1 with non-punctuation characters.
    # The punc model adds punctuation to text AFTER ASR, so
    # len(text) > len(timestamps). We skip punctuation when mapping.
    timestamps = result_data.get("timestamp", [])
    text = result_data.get("text", "")
    punct = set("。？！，,?!；;、：:\"\"''（）()《》【】 ")

    if timestamps and text:
        ts_idx = 0
        current_text = ""
        current_start_ms = timestamps[0][0]
        current_end_ms = timestamps[0][1]

        for char in text:
            current_text += char

            if char not in punct and ts_idx < len(timestamps):
                current_end_ms = timestamps[ts_idx][1]
                ts_idx += 1

            if char in "。？！，,?!；;":
                segments.append(TranscriptSegment(
                    start=current_start_ms / 1000.0,
                    end=current_end_ms / 1000.0,
                    text=current_text.strip(),
                ))
                current_text = ""
                if ts_idx < len(timestamps):
                    current_start_ms = timestamps[ts_idx][0]

        if current_text.strip():
            segments.append(TranscriptSegment(
                start=current_start_ms / 1000.0,
                end=timestamps[-1][1] / 1000.0 if timestamps else 0.0,
                text=current_text.strip(),
            ))
        return segments

    # Fallback: full text without timing
    if text:
        return [TranscriptSegment(start=0.0, end=0.0, text=text)]

    return []


# ---------------------------------------------------------------------------
# Whisper engine (default — lightweight, PyInstaller compatible)
# ---------------------------------------------------------------------------

_whisper_model = None
_whisper_lock = threading.Lock()


def _get_whisper_model(model_name: str = "small"):
    """Lazy-load Whisper model (singleton, thread-safe).

    First call downloads model (~461MB for 'small'). Subsequent calls use cache.
    """
    global _whisper_model
    with _whisper_lock:
        if _whisper_model is not None:
            return _whisper_model
        try:
            import whisper
            logger.info("加载 Whisper %s 模型（首次需下载约 461MB）...", model_name)
            _whisper_model = whisper.load_model(model_name)
            logger.info("Whisper %s 模型加载完成", model_name)
            return _whisper_model
        except Exception as exc:
            logger.warning("Whisper 加载失败: %s", exc)
            return None


def _transcribe_whisper(video_path: str) -> list[TranscriptSegment]:
    """Transcribe using OpenAI Whisper (local, no API key needed)."""
    model = _get_whisper_model()
    if model is None:
        raise RuntimeError("Whisper 模型加载失败")

    result = model.transcribe(
        video_path,
        language="zh",
        task="transcribe",
        verbose=False,
    )

    segments: list[TranscriptSegment] = []
    for seg in result.get("segments", []):
        text = seg.get("text", "").strip()
        if text:
            segments.append(TranscriptSegment(
                start=seg.get("start", 0.0),
                end=seg.get("end", 0.0),
                text=text,
            ))
    return segments


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def transcribe_video(
    video_path: str,
    funasr_url: str = "http://localhost:10095",
    hotwords: str = "",
    enable_diarization: bool = True,
) -> list[TranscriptSegment]:
    """Transcribe video. Priority: FunASR (if installed) → Whisper → HTTP.

    Args:
        video_path: Path to the input video file.
        hotwords: Space-separated hotwords (FunASR only).
        enable_diarization: Enable speaker detection (FunASR only).

    Returns:
        List of TranscriptSegment objects.
    """
    video_path_obj = Path(video_path)
    if not video_path_obj.exists():
        raise FileNotFoundError(f"视频文件不存在: {video_path_obj}")

    # Priority 1: FunASR (better for Chinese, supports hotwords + diarization)
    try:
        result = _transcribe_local(video_path, hotwords=hotwords, enable_diarization=enable_diarization)
        if result:
            logger.info("语音识别完成 (FunASR): %d 段", len(result))
            return result
    except Exception as exc:
        logger.info("FunASR 不可用，使用 Whisper: %s", exc)

    # Priority 2: Whisper (always works, auto-downloads model)
    try:
        import asyncio
        result = await asyncio.to_thread(_transcribe_whisper, video_path)
        if result:
            logger.info("语音识别完成 (Whisper): %d 段", len(result))
            return result
    except Exception as exc:
        logger.warning("Whisper 识别失败: %s", exc)

    # Priority 3: HTTP fallback
    try:
        return await _transcribe_http(video_path, funasr_url)
    except Exception as exc:
        raise RuntimeError("语音识别失败，请检查网络连接或联系管理员") from exc


async def _transcribe_http(
    video_path: str,
    funasr_url: str,
) -> list[TranscriptSegment]:
    """Fallback: extract audio → send to FunASR HTTP API."""
    import asyncio
    import tempfile
    import httpx

    # Extract audio
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        audio_path = tmp.name

    process = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        audio_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    if process.returncode != 0:
        error_msg = stderr.decode().strip() if stderr else "Unknown error"
        raise RuntimeError(f"ffmpeg audio extraction failed: {error_msg}")

    try:
        api_url = f"{funasr_url}/api/asr"
        timeout = httpx.Timeout(120.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            with open(audio_path, "rb") as f:
                response = await client.post(api_url, files={"file": ("audio.wav", f, "audio/wav")})

        if response.status_code != 200:
            raise RuntimeError(f"语音识别服务连接失败 (HTTP {response.status_code})，请确认 FunASR 服务已启动: {funasr_url}")
        data = response.json()
        segments = data.get("segments", [])
        return [
            TranscriptSegment(start=s["start"], end=s["end"], text=s["text"])
            for s in segments
        ]
    finally:
        Path(audio_path).unlink(missing_ok=True)
