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


def _get_local_model():
    """Lazy-load FunASR model (singleton, thread-safe). Returns None if unavailable."""
    global _local_model, _model_load_attempted
    with _model_lock:
        if _model_load_attempted:
            return _local_model
        _model_load_attempted = True
        try:
            from funasr import AutoModel
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info("Loading FunASR model (device=%s)...", device)
            _local_model = AutoModel(
                model="paraformer-zh",
                vad_model="fsmn-vad",
                punc_model="ct-punc",
                device=device,
                disable_update=True,
            )
            logger.info("FunASR model loaded successfully")
        except Exception as exc:
            logger.warning("FunASR local model unavailable: %s", exc)
            _local_model = None
        return _local_model


def _transcribe_local(
    video_path: str,
    hotwords: str = "",
) -> list[TranscriptSegment]:
    """Transcribe using local FunASR model (VF1 mode — fast)."""
    model = _get_local_model()
    if model is None:
        raise RuntimeError("Local FunASR model not available")

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
            segments.append(TranscriptSegment(
                start=item["start"] / 1000.0,
                end=item["end"] / 1000.0,
                text=item["text"].strip(),
            ))
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


async def transcribe_video(
    video_path: str,
    funasr_url: str = "http://localhost:10095",
    hotwords: str = "",
) -> list[TranscriptSegment]:
    """Transcribe video — uses local model (fast) with HTTP fallback.

    Args:
        video_path: Path to the input video file.
        funasr_url: Base URL of FunASR HTTP API (fallback only).
        hotwords: Space-separated hotwords to boost recognition accuracy.

    Returns:
        List of TranscriptSegment objects.
    """
    video_path_obj = Path(video_path)
    if not video_path_obj.exists():
        raise FileNotFoundError(f"Video file not found: {video_path_obj}")

    # Try local model first (10x faster than HTTP)
    try:
        result = _transcribe_local(video_path, hotwords=hotwords)
        if result:
            return result
    except Exception as exc:
        logger.warning("Local FunASR failed, falling back to HTTP: %s", exc)

    # Fallback: HTTP API
    return await _transcribe_http(video_path, funasr_url)


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

        data = response.json()
        segments = data.get("segments", [])
        return [
            TranscriptSegment(start=s["start"], end=s["end"], text=s["text"])
            for s in segments
        ]
    finally:
        Path(audio_path).unlink(missing_ok=True)
