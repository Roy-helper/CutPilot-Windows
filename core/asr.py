"""FunASR integration for speech-to-text transcription.

CutPilot: Direct local model call, auto-detects GPU/CPU.
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
        {"installed": bool, "models_cached": bool, "engine": str, "message": str,
         "whisper_available": bool, "funasr_available": bool, "cloud_available": bool}
    """
    result = {"installed": False, "models_cached": False, "engine": "none",
              "message": "", "whisper_available": False, "funasr_available": False,
              "cloud_available": False}

    # Check cloud API (DashScope) — needs API key (built-in or user)
    try:
        has_key = False
        try:
            from core.builtin_keys import DASHSCOPE_API_KEY
            has_key = bool(DASHSCOPE_API_KEY)
        except ImportError:
            from core.user_settings import load_user_settings
            settings = load_user_settings()
            has_key = bool(settings.get("api_key", ""))
        try:
            import dashscope  # noqa: F401
            result["cloud_available"] = has_key
            if has_key:
                result["installed"] = True
                result["models_cached"] = True
                result["engine"] = "cloud"
                result["message"] = "语音识别就绪 (云端)"
        except ImportError:
            pass
    except Exception:
        pass

    # Check Whisper
    try:
        import whisper  # noqa: F401
        result["whisper_available"] = True
        if not result["installed"]:
            result["installed"] = True
            result["engine"] = "whisper"
            result["models_cached"] = True
            result["message"] = "语音识别就绪 (Whisper 本地)"
    except ImportError:
        pass

    # Check FunASR
    try:
        import funasr  # noqa: F401
        result["funasr_available"] = True
        if not result["installed"]:
            result["installed"] = True
            result["engine"] = "funasr"
            result["message"] = "语音识别就绪 (FunASR 本地)"
    except ImportError:
        pass

    if not result["installed"]:
        result["message"] = "语音识别不可用: 请配置 API Key 或安装本地引擎"

    return result


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
# faster-whisper engine (default — lightweight, no torch dependency)
# ---------------------------------------------------------------------------

_fw_model = None
_fw_lock = threading.Lock()

_MODEL_DIR = Path.home() / ".cutpilot" / "models"


def get_model_status(engine: str = "faster-whisper") -> dict:
    """Check if ASR model is downloaded for the given engine.

    Args:
        engine: "faster-whisper" or "funasr".

    Returns:
        {"ready": bool, "model_path": str, "message": str}
    """
    if engine == "funasr":
        return _get_funasr_model_status()

    model_dir = _MODEL_DIR / "faster-whisper-small"
    if model_dir.exists() and (model_dir / "model.bin").exists():
        return {"ready": True, "model_path": str(model_dir),
                "message": "语音模型就绪"}
    return {"ready": False, "model_path": str(model_dir),
            "message": "需要下载语音模型（约 500MB）"}


def _get_funasr_model_status() -> dict:
    """Check if FunASR dependencies and models are available."""
    # Check required packages
    missing: list[str] = []
    for pkg in ("funasr", "torch", "torchaudio"):
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if missing:
        return {
            "ready": False,
            "model_path": "",
            "message": f"缺少依赖: {', '.join(missing)}（运行 pip install {' '.join(missing)}）",
        }

    # Packages installed — check if model files are cached
    # FunASR caches models under ~/.cache/modelscope/hub/
    model_cache = Path.home() / ".cache" / "modelscope" / "hub" / "iic"
    paraformer_dir = model_cache / "speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch"
    if paraformer_dir.exists():
        return {"ready": True, "model_path": str(paraformer_dir),
                "message": "FunASR 模型就绪"}

    # Also check for the simpler paraformer-zh model
    simple_dir = model_cache / "speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch"
    if simple_dir.exists():
        return {"ready": True, "model_path": str(simple_dir),
                "message": "FunASR 模型就绪"}

    return {"ready": False, "model_path": str(model_cache),
            "message": "FunASR 依赖已安装，需要下载模型（约 2GB）"}


def download_model(engine: str = "faster-whisper") -> dict:
    """Download ASR model for the given engine.

    Args:
        engine: "faster-whisper" or "funasr".

    Returns:
        {"success": bool, "message": str}
    """
    if engine == "funasr":
        return _download_funasr_model()

    import os
    # Use Chinese mirror for HuggingFace (blocked in mainland China)
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

    _MODEL_DIR.mkdir(parents=True, exist_ok=True)
    output_dir = str(_MODEL_DIR / "faster-whisper-small")

    try:
        from huggingface_hub import snapshot_download
        logger.info("下载语音模型到 %s (使用国内镜像)...", output_dir)
        snapshot_download(
            "Systran/faster-whisper-small",
            local_dir=output_dir,
            local_dir_use_symlinks=False,
        )
        logger.info("语音模型下载完成")
        return {"success": True, "message": "语音模型下载完成！"}
    except Exception as e:
        logger.exception("模型下载失败")
        err = str(e)
        if "connect" in err.lower() or "network" in err.lower():
            return {"success": False, "message": "网络连接失败，请检查网络后重试"}
        return {"success": False, "message": f"下载失败: {err[:100]}"}


def _download_funasr_model() -> dict:
    """Download FunASR model by triggering a dry-run model load.

    FunASR auto-downloads from ModelScope on first use.
    """
    # First check dependencies are installed
    missing: list[str] = []
    for pkg in ("funasr", "torch", "torchaudio"):
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if missing:
        return {
            "success": False,
            "message": f"请先安装依赖: pip install {' '.join(missing)}",
        }

    try:
        from funasr import AutoModel
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info("下载 FunASR 模型 (首次约 2GB)...")
        AutoModel(
            model="iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
            vad_model="fsmn-vad",
            punc_model="ct-punc",
            spk_model="cam++",
            device=device,
            disable_update=False,
        )
        logger.info("FunASR 模型下载完成")
        return {"success": True, "message": "FunASR 模型下载完成！"}
    except Exception as e:
        logger.exception("FunASR 模型下载失败")
        err = str(e)
        if "connect" in err.lower() or "network" in err.lower():
            return {"success": False, "message": "网络连接失败，请检查网络后重试"}
        return {"success": False, "message": f"下载失败: {err[:100]}"}


def _get_fw_model():
    """Lazy-load faster-whisper model (singleton, thread-safe)."""
    global _fw_model
    with _fw_lock:
        if _fw_model is not None:
            return _fw_model

        status = get_model_status()
        if not status["ready"]:
            raise RuntimeError("语音模型未下载，请在设置页点击「下载语音模型」")

        try:
            from faster_whisper import WhisperModel
            logger.info("加载语音模型...")
            _fw_model = WhisperModel(
                status["model_path"],
                device="cpu",
                compute_type="int8",
            )
            logger.info("语音模型加载完成")
            return _fw_model
        except Exception as exc:
            logger.warning("语音模型加载失败: %s", exc)
            return None


def _transcribe_faster_whisper(video_path: str) -> list[TranscriptSegment]:
    """Transcribe using faster-whisper (local, no torch needed)."""
    model = _get_fw_model()
    if model is None:
        raise RuntimeError("语音模型未就绪")

    segments_iter, info = model.transcribe(
        video_path, language="zh", vad_filter=True,
    )

    segments: list[TranscriptSegment] = []
    for seg in segments_iter:
        text = seg.text.strip()
        if text:
            segments.append(TranscriptSegment(
                start=seg.start,
                end=seg.end,
                text=text,
            ))
    return segments


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def transcribe_video(
    video_path: str,
    hotwords: str = "",
    enable_diarization: bool = True,
    engine: str = "faster-whisper",
) -> list[TranscriptSegment]:
    """Transcribe video using the specified engine.

    Args:
        video_path: Path to the input video file.
        hotwords: Space-separated hotwords (FunASR only).
        enable_diarization: Enable speaker detection (FunASR only).
        engine: "faster-whisper" (default, lightweight) or "funasr" (better Chinese).

    Returns:
        List of TranscriptSegment objects.
    """
    video_path_obj = Path(video_path)
    if not video_path_obj.exists():
        raise FileNotFoundError(f"视频文件不存在: {video_path_obj}")

    if engine == "funasr":
        # FunASR path: use local FunASR model
        try:
            result = _transcribe_local(video_path, hotwords=hotwords, enable_diarization=enable_diarization)
            if result:
                logger.info("语音识别完成 (FunASR): %d 段", len(result))
                return result
        except Exception as exc:
            logger.warning("FunASR 识别失败: %s", exc)
            raise RuntimeError(f"FunASR 识别失败: {exc}") from exc
    else:
        # faster-whisper path (default)
        try:
            import asyncio
            result = await asyncio.to_thread(_transcribe_faster_whisper, video_path)
            if result:
                logger.info("语音识别完成 (Whisper): %d 段", len(result))
                return result
        except Exception as exc:
            logger.warning("Whisper 不可用: %s", exc)

        # Fallback: try FunASR if faster-whisper fails
        try:
            result = _transcribe_local(video_path, hotwords=hotwords, enable_diarization=enable_diarization)
            if result:
                logger.info("语音识别完成 (FunASR fallback): %d 段", len(result))
                return result
        except Exception as exc:
            logger.info("FunASR fallback 也不可用: %s", exc)

    raise RuntimeError("语音模型未下载，请在设置页点击「下载语音模型」")
