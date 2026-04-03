"""FunASR integration for speech-to-text transcription.

CutPilot: Direct local model call, auto-detects GPU/CPU.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Callable

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


def get_model_status(engine: str = "faster-whisper", **kwargs) -> dict:
    """Check if ASR model is downloaded for the given engine.

    Args:
        engine: "faster-whisper" or "funasr".

    Returns:
        {"ready": bool, "model_path": str, "message": str}
    """
    if engine == "funasr":
        return _get_funasr_model_status()

    model_size = kwargs.get("model_size", "small")
    model_dir = _MODEL_DIR / f"faster-whisper-{model_size}"
    if model_dir.exists() and (model_dir / "model.bin").exists():
        return {"ready": True, "model_path": str(model_dir),
                "message": f"语音模型就绪 ({model_size})"}
    size_map = {"tiny": "~75MB", "small": "~500MB", "medium": "~1.5GB"}
    return {"ready": False, "model_path": str(model_dir),
            "message": f"需要下载语音模型（{size_map.get(model_size, '~500MB')}）"}


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


def download_model(
    engine: str = "faster-whisper",
    on_progress: Callable[[int], None] | None = None,
    **kwargs,
) -> dict:
    """Download ASR model for the given engine.

    Args:
        engine: "faster-whisper" or "funasr".
        on_progress: Optional callback ``(percent: int)`` for download progress.

    Returns:
        {"success": bool, "message": str}
    """
    if engine == "funasr":
        return _download_funasr_model()

    import os
    # Use Chinese mirror for HuggingFace (blocked in mainland China)
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
    # Connection timeout for huggingface_hub (uses requests internally)
    os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = "30"

    _MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model_size = kwargs.get("model_size", "small")
    output_dir = str(_MODEL_DIR / f"faster-whisper-{model_size}")
    mirror_url = f"https://hf-mirror.com/Systran/faster-whisper-{model_size}"

    _manual_download_msg = (
        f"模型下载失败。请手动下载后放到以下目录：\n"
        f"{output_dir}\n"
        f"下载地址：{mirror_url}"
    )

    if on_progress:
        on_progress(0)

    try:
        from huggingface_hub import snapshot_download
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

        logger.info("下载语音模型到 %s (使用国内镜像)...", output_dir)

        # Run download in thread with 10-minute timeout
        def _do_download() -> None:
            snapshot_download(
                f"Systran/faster-whisper-{model_size}",
                local_dir=output_dir,
                local_dir_use_symlinks=False,
            )

        # Start download with progress polling
        import threading
        done_event = threading.Event()

        def _poll_progress() -> None:
            """Poll output dir size to estimate progress."""
            # faster-whisper-small is ~460MB
            expected_bytes = 460 * 1024 * 1024
            while not done_event.is_set():
                if on_progress:
                    try:
                        total = sum(
                            f.stat().st_size
                            for f in Path(output_dir).rglob("*")
                            if f.is_file()
                        )
                        pct = min(90, int(total / expected_bytes * 90))
                        on_progress(pct)
                    except Exception:
                        pass
                done_event.wait(5)

        progress_thread = threading.Thread(target=_poll_progress, daemon=True)
        progress_thread.start()

        try:
            with ThreadPoolExecutor(1) as pool:
                future = pool.submit(_do_download)
                future.result(timeout=600)  # 10 minutes
        finally:
            done_event.set()
            progress_thread.join(timeout=2)

        if on_progress:
            on_progress(100)

        logger.info("语音模型下载完成")
        return {"success": True, "message": "语音模型下载完成！"}
    except FuturesTimeout:
        logger.error("模型下载超时（10分钟）")
        return {"success": False, "message": f"下载超时（10分钟）。\n{_manual_download_msg}"}
    except Exception as e:
        logger.exception("模型下载失败")
        err = str(e)
        if "connect" in err.lower() or "network" in err.lower() or "timeout" in err.lower():
            return {"success": False, "message": f"网络连接失败。\n{_manual_download_msg}"}
        return {"success": False, "message": f"下载失败: {err[:100]}\n{_manual_download_msg}"}


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


# Track which model size is actually loaded so we can invalidate on change
_fw_loaded_size: str | None = None
_fw_auto_downgraded: bool = False


def _detect_device_and_compute() -> tuple[str, str]:
    """Detect the best device and compute type for faster-whisper.

    Returns:
        (device, compute_type) — e.g. ("cuda", "float16") or ("cpu", "int8").
    """
    try:
        import ctranslate2
        cuda_types = ctranslate2.get_supported_compute_types("cuda")
        if cuda_types:  # non-empty set means CUDA is available
            compute = "float16" if "float16" in cuda_types else "int8"
            return "cuda", compute
    except Exception:
        pass
    return "cpu", "int8"


def _get_gpu_name_for_log() -> str:
    """Best-effort GPU name for diagnostic logging."""
    try:
        import ctranslate2
        cuda_types = ctranslate2.get_supported_compute_types("cuda")
        if cuda_types:
            try:
                from core.subprocess_utils import run_hidden
                r = run_hidden(
                    ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                    capture_output=True, text=True, timeout=5,
                )
                if r.returncode == 0 and r.stdout.strip():
                    return r.stdout.strip().splitlines()[0]
            except Exception:
                pass
            return "CUDA (unknown model)"
    except Exception:
        pass
    return "none"


def _get_fw_model(model_size: str = "small"):
    """Lazy-load faster-whisper model (singleton, thread-safe).

    Args:
        model_size: "tiny", "small", or "medium".

    Auto-downgrades medium → small when running on CPU (too slow otherwise).
    Logs full diagnostics: model size, device, compute_type, GPU model.
    """
    global _fw_model, _fw_loaded_size, _fw_auto_downgraded
    with _fw_lock:
        # Return cached model if same size
        if _fw_model is not None and _fw_loaded_size == model_size:
            return _fw_model

        # Detect device
        device, compute_type = _detect_device_and_compute()
        gpu_name = _get_gpu_name_for_log()

        # Auto-downgrade: medium on CPU is extremely slow
        _fw_auto_downgraded = False
        actual_size = model_size
        if device == "cpu" and model_size == "medium":
            actual_size = "small"
            _fw_auto_downgraded = True
            logger.warning(
                "ASR 自动降级: medium → small (CPU 运行 medium 模型过慢)"
            )

        status = get_model_status(model_size=actual_size)
        if not status["ready"]:
            # If downgraded but small not downloaded either, try tiny
            if _fw_auto_downgraded:
                status = get_model_status(model_size="tiny")
                if status["ready"]:
                    actual_size = "tiny"
                    logger.warning("small 模型也未下载，降级到 tiny")
            if not status["ready"]:
                raise RuntimeError("语音模型未下载，请在设置页点击「下载语音模型」")

        # Log diagnostics
        logger.info(
            "ASR 诊断: model_size=%s, device=%s, compute_type=%s, gpu=%s, "
            "model_path=%s",
            actual_size, device, compute_type, gpu_name,
            status["model_path"],
        )

        try:
            from faster_whisper import WhisperModel
            _fw_model = WhisperModel(
                status["model_path"],
                device=device,
                compute_type=compute_type,
            )
            _fw_loaded_size = actual_size
            logger.info("语音模型加载完成 (%s, %s)", actual_size, device)
            return _fw_model
        except Exception as exc:
            logger.warning("语音模型加载失败: %s", exc)
            # If CUDA failed, fall back to CPU
            if device == "cpu":
                return None
            logger.info("CUDA 加载失败，回退到 CPU")
            try:
                _fw_model = WhisperModel(
                    status["model_path"],
                    device="cpu",
                    compute_type="int8",
                )
                _fw_loaded_size = actual_size
                logger.info("语音模型加载完成 (%s, cpu fallback)", actual_size)
                return _fw_model
            except Exception as exc2:
                logger.warning("CPU fallback 也失败: %s", exc2)
                return None


def _transcribe_faster_whisper(
    video_path: str,
    model_size: str = "small",
    on_progress: Callable[[str, int], None] | None = None,
) -> list[TranscriptSegment]:
    """Transcribe using faster-whisper with streaming progress.

    Args:
        video_path: Path to video/audio file.
        model_size: Model size to use (may be auto-downgraded).
        on_progress: Optional callback ``(label, percent)`` for per-segment progress.
    """
    model = _get_fw_model(model_size)
    if model is None:
        raise RuntimeError("语音模型未就绪")

    # If auto-downgraded, the caller should know
    if _fw_auto_downgraded and on_progress:
        on_progress("检测到无 GPU 加速，已自动切换至 small 模型提升速度", 10)

    segments_iter, info = model.transcribe(
        video_path, language="zh", vad_filter=True,
    )

    # Stream segments with progress — estimate from audio duration
    duration = info.duration if info.duration > 0 else 1.0
    segments: list[TranscriptSegment] = []
    for seg in segments_iter:
        text = seg.text.strip()
        if text:
            segments.append(TranscriptSegment(
                start=seg.start,
                end=seg.end,
                text=text,
            ))
            if on_progress:
                # Map segment end time to 10%-28% range (ASR is 10-30 in pipeline)
                pct = min(28, 10 + int((seg.end / duration) * 18))
                on_progress(f"正在识别语音... ({len(segments)} 段)", pct)
    return segments


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def transcribe_video(
    video_path: str,
    hotwords: str = "",
    enable_diarization: bool = True,
    engine: str = "faster-whisper",
    model_size: str = "small",
    on_progress: Callable[[str, int], None] | None = None,
) -> list[TranscriptSegment]:
    """Transcribe video using the specified engine.

    Args:
        video_path: Path to the input video file.
        hotwords: Space-separated hotwords (FunASR only).
        enable_diarization: Enable speaker detection (FunASR only).
        engine: "faster-whisper" (default, lightweight) or "funasr" (better Chinese).
        model_size: Model size for faster-whisper: "tiny", "small", or "medium".
        on_progress: Optional callback ``(label, percent)`` for streaming progress.

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
            result = await asyncio.to_thread(
                _transcribe_faster_whisper, video_path,
                model_size=model_size, on_progress=on_progress,
            )
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
