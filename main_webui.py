"""CutPilot — Web UI launcher via pywebview.

Opens a native window rendering the Vue 3 + Tailwind frontend.
Python backend functions are exposed to JavaScript via the pywebview API bridge.
"""
from __future__ import annotations

import asyncio
import logging
import sys
import threading
from pathlib import Path

import webview

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Fix SSL certificates for PyInstaller on macOS
# Without this, urllib/requests fails with CERTIFICATE_VERIFY_FAILED
try:
    import certifi
    import os
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
except ImportError:
    pass

_DIST_DIR = Path(__file__).parent / "webui" / "dist"

# Background event loop for async pipeline calls
_loop: asyncio.AbstractEventLoop | None = None


def _get_loop() -> asyncio.AbstractEventLoop:
    global _loop
    if _loop is None:
        _loop = asyncio.new_event_loop()
        t = threading.Thread(target=_loop.run_forever, daemon=True)
        t.start()
    return _loop


def _run_async(coro):
    """Run an async coroutine from the sync pywebview bridge."""
    loop = _get_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result()


class PythonBridge:
    """API bridge exposed to JavaScript as ``window.pywebview.api``.

    Every public method is callable from the Vue frontend.
    """

    def __init__(self) -> None:
        self._window: webview.Window | None = None
        self._processing = False
        self._cancel_event = threading.Event()

    def set_window(self, window: webview.Window) -> None:
        self._window = window

    # ── Health ──────────────────────────────────────────────

    def ping(self) -> str:
        return "pong"

    # ── Hardware Detection ──────────────────────────────────

    def get_encoder_info(self) -> dict:
        """Return detected hardware encoder info."""
        from core.hwaccel import get_encoder_info
        info = get_encoder_info()
        return info.model_dump()

    def get_max_parallel(self) -> int:
        """Return recommended parallel encode count."""
        from core.hwaccel import get_max_parallel
        return get_max_parallel()

    def run_benchmark(self) -> dict:
        """Run system benchmark and return detailed parallel capacity info."""
        from core.hwaccel import benchmark_parallel
        return benchmark_parallel()

    # ── ASR Status ───────────────────────────────────────────

    def check_asr_status(self, engine: str = "") -> dict:
        """Check if ASR model is downloaded and ready.

        Args:
            engine: "faster-whisper" or "funasr". If empty, reads from user settings.
        """
        try:
            if not engine:
                from core.user_settings import load_user_settings
                engine = load_user_settings().get("asr_engine", "faster-whisper")
            from core.asr import get_model_status
            return get_model_status(engine=engine)
        except Exception as e:
            return {"ready": False, "message": str(e)}

    def download_asr_model(self, engine: str = "") -> dict:
        """Download ASR model for the given engine.

        Args:
            engine: "faster-whisper" or "funasr". If empty, reads from user settings.
        """
        try:
            if not engine:
                from core.user_settings import load_user_settings
                engine = load_user_settings().get("asr_engine", "faster-whisper")
            from core.asr import download_model
            return download_model(engine=engine)
        except Exception as e:
            logger.exception("模型下载失败")
            return {"success": False, "message": f"下载失败: {e}"}

    # ── License ─────────────────────────────────────────────

    def get_machine_id(self) -> str:
        from core.license import get_machine_id
        return get_machine_id()

    def get_license_info(self) -> dict:
        from core.license import get_license_info
        return get_license_info()

    def activate_license(self, code: str) -> dict:
        """Validate and activate a license code."""
        from core.license import activate
        success, message = activate(code)
        return {"success": success, "message": message}

    # ── Settings ────────────────────────────────────────────

    def load_settings(self) -> dict:
        from core.user_settings import load_user_settings
        return load_user_settings()

    def save_settings(self, settings: dict) -> dict:
        from core.user_settings import save_user_settings
        try:
            save_user_settings(settings)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Providers ───────────────────────────────────────────

    def get_providers(self) -> list[dict]:
        from core.providers import PROVIDERS
        return [p.model_dump() for p in PROVIDERS]

    # ── File Operations ─────────────────────────────────────

    def select_files(self) -> list[str]:
        """Open native file picker and return selected video paths."""
        if not self._window:
            return []
        result = self._window.create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=True,
            file_types=(
                "视频文件 (*.mp4;*.mov;*.avi;*.mkv;*.flv;*.wmv)",
                "所有文件 (*.*)",
            ),
        )
        return list(result) if result else []

    def select_directory(self) -> str:
        """Open native directory picker and return selected path."""
        if not self._window:
            return ""
        result = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        return result[0] if result else ""

    def open_folder(self, path: str) -> dict:
        """Open a folder in Finder/Explorer."""
        import subprocess
        try:
            p = Path(path)
            target = p if p.is_dir() else p.parent
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(target)])
            elif sys.platform == "win32":
                subprocess.Popen(["explorer", str(target)])
            else:
                subprocess.Popen(["xdg-open", str(target)])
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── History ─────────────────────────────────────────────

    def get_history(self) -> list[dict]:
        from core.history import load_history
        return load_history()

    def clear_history(self) -> dict:
        from core.history import clear_history
        try:
            clear_history()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def delete_history_entry(self, timestamp: str) -> dict:
        from core.history import delete_history_entry
        try:
            delete_history_entry(timestamp)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── AI Connection Test ──────────────────────────────────

    def test_connection(self, provider: str, api_key: str,
                        base_url: str = "", model: str = "") -> dict:
        """Test AI API connection with given credentials."""
        from core.providers import get_provider
        from openai import OpenAI

        preset = get_provider(provider)
        if not preset and not base_url:
            return {"success": False, "error": "未知供应商"}

        url = base_url or (preset.base_url if preset else "")
        mdl = model or (preset.model if preset else "")

        try:
            client = OpenAI(api_key=api_key, base_url=url)
            resp = client.chat.completions.create(
                model=mdl,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5,
            )
            return {"success": True, "model": mdl, "reply": resp.choices[0].message.content}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Pipeline ────────────────────────────────────────────

    def process_video(self, video_path: str, settings_override: dict | None = None) -> dict:
        """Run the full pipeline on a video file.

        Sends progress updates to the frontend via JS evaluation.
        Returns ProcessResult as dict.
        """
        if self._processing:
            return {"success": False, "error": "已有任务在处理中"}

        from core.user_settings import build_config_from_settings
        config = build_config_from_settings()
        if not config.api_key:
            return {"success": False, "error": "请先在设置页配置 API Key"}

        self._processing = True
        self._cancel_event.clear()
        try:
            from core.config import CutPilotConfig
            from core.cache_manager import CacheManager
            from core.pipeline import process_video
            from core.history import add_history_entry, HistoryEntry
            from datetime import datetime
            import time

            if settings_override:
                config = CutPilotConfig(**{**config.model_dump(), **settings_override})

            cache = CacheManager()

            def on_progress(label: str, percent: int) -> None:
                if self._window:
                    js = f'window.dispatchEvent(new CustomEvent("pipeline-progress", {{detail: {{label: "{label}", percent: {percent}}}}}))'
                    self._window.evaluate_js(js)

            hotwords = ""
            user_settings = self.load_settings()
            if "hotwords" in user_settings:
                hotwords = user_settings["hotwords"]

            start = time.time()
            result = _run_async(process_video(
                video_path=Path(video_path),
                config=config,
                on_progress=on_progress,
                cache=cache,
                hotwords=hotwords,
                cancel_event=self._cancel_event,
            ))
            elapsed = time.time() - start

            result_dict = result.model_dump()

            # Record history
            entry = HistoryEntry(
                video_name=Path(video_path).name,
                video_path=video_path,
                timestamp=datetime.now().isoformat(),
                success=result.success,
                error=result.error,
                versions_count=len(result.versions),
                output_files=[str(f) for f in result.output_files] if result.output_files else [],
                approach_tags=[v.approach_tag for v in result.versions] if result.versions else [],
                duration_sec=round(elapsed, 1),
            )
            add_history_entry(entry)

            return result_dict
        except Exception as e:
            logger.exception("Pipeline error")
            return {"success": False, "error": str(e), "versions": [], "output_files": []}
        finally:
            self._processing = False

    def is_processing(self) -> bool:
        return self._processing

    def cancel_processing(self) -> dict:
        """Cancel the current processing task."""
        if not self._processing:
            return {"success": False, "error": "没有正在进行的任务"}
        self._cancel_event.set()
        logger.info("Processing cancellation requested")
        return {"success": True}

    def process_batch(self, video_paths: list[str]) -> list[dict]:
        """Process multiple videos in parallel with auto-detected concurrency.

        Sends per-video progress events to the frontend.
        Returns list of ProcessResult dicts.
        """
        if self._processing:
            return [{"success": False, "error": "已有任务在处理中"}]

        from core.user_settings import build_config_from_settings
        config = build_config_from_settings()
        if not config.api_key:
            return [{"success": False, "error": "请先在设置页配置 API Key", "versions": [], "output_files": []}]

        self._processing = True
        self._cancel_event.clear()
        try:
            from core.cache_manager import CacheManager
            from core.pipeline import process_batch
            from core.history import add_history_entry, HistoryEntry
            from core.hwaccel import get_max_parallel
            from datetime import datetime
            import time

            cache = CacheManager()
            max_par = get_max_parallel()

            hotwords = ""
            user_settings = self.load_settings()
            if "hotwords" in user_settings:
                hotwords = user_settings["hotwords"]

            def on_progress(video_name: str, index: int, percent: int) -> None:
                if self._window:
                    safe_name = video_name.replace('"', '\\"')
                    js = (
                        f'window.dispatchEvent(new CustomEvent("pipeline-progress", '
                        f'{{detail: {{label: "{safe_name}", percent: {percent}, index: {index}, total: {len(video_paths)}}}}}))'
                    )
                    self._window.evaluate_js(js)

            start = time.time()
            paths = [Path(p) for p in video_paths]
            results = _run_async(process_batch(
                video_paths=paths,
                config=config,
                on_progress=on_progress,
                cache=cache,
                hotwords=hotwords,
                max_parallel=max_par,
                cancel_event=self._cancel_event,
            ))
            elapsed = time.time() - start

            result_dicts = []
            for i, result in enumerate(results):
                # Record history per video
                entry = HistoryEntry(
                    video_name=paths[i].name,
                    video_path=video_paths[i],
                    timestamp=datetime.now().isoformat(),
                    success=result.success,
                    error=result.error,
                    versions_count=len(result.versions),
                    output_files=[str(f) for f in result.output_files] if result.output_files else [],
                    approach_tags=[v.approach_tag for v in result.versions] if result.versions else [],
                    duration_sec=round(elapsed / len(paths), 1),
                )
                add_history_entry(entry)
                result_dicts.append(result.model_dump())

            return result_dicts
        except Exception as e:
            logger.exception("Batch pipeline error")
            error_result = {"success": False, "error": str(e), "versions": [], "output_files": []}
            return [error_result for _ in video_paths]
        finally:
            self._processing = False

    # ── Export ───────────────────────────────────────────────

    def export_versions(self, video_path: str, version_ids: list[int],
                        options: dict | None = None) -> dict:
        """Export specific versions of a processed video."""
        try:
            from core.editor import cut_versions
            from core.models import ExportOptions, ScriptVersion
            from core.cache_manager import CacheManager
            from core.user_settings import build_config_from_settings

            config = build_config_from_settings()
            cache = CacheManager()

            # Load cached inspector results (approved versions)
            # Cache stores a plain list of version dicts
            inspector_data = cache.load(Path(video_path), "inspector")
            if not inspector_data:
                return {"success": False, "error": "未找到缓存的版本数据，请先处理视频"}

            version_list = inspector_data if isinstance(inspector_data, list) else inspector_data.get("versions", [])
            all_versions = [ScriptVersion(**v) for v in version_list]
            selected = [v for v in all_versions if v.version_id in version_ids]

            if not selected:
                return {"success": False, "error": "未找到选中的版本"}

            # Cache stores a plain list of sentence dicts
            asr_data = cache.load(Path(video_path), "asr")
            if not asr_data:
                return {"success": False, "error": "未找到 ASR 缓存"}

            from core.models import Sentence
            sentence_list = asr_data if isinstance(asr_data, list) else asr_data.get("sentences", [])
            sentences = [Sentence(**s) for s in sentence_list]

            export_opts = None
            if options:
                export_opts = [ExportOptions(version_id=vid, **options) for vid in version_ids]

            output = _run_async(cut_versions(
                video_path=Path(video_path),
                versions=selected,
                sentences=sentences,
                config=config,
                export_options=export_opts,
            ))
            return {"success": True, "files": output}
        except Exception as e:
            logger.exception("Export error")
            return {"success": False, "error": str(e)}

    # ── Thumbnail ────────────────────────────────────────────

    def generate_thumbnail(self, video_path: str, time_sec: float = 1.0) -> str:
        """Extract a frame from video at given timestamp, return as base64 data URI."""
        import base64
        import os
        import subprocess
        import tempfile

        tmp = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
        tmp.close()
        try:
            subprocess.run([
                'ffmpeg', '-y', '-ss', str(time_sec), '-i', video_path,
                '-frames:v', '1', '-q:v', '3',
                '-vf', 'scale=480:-1',
                tmp.name
            ], capture_output=True, timeout=10)

            with open(tmp.name, 'rb') as f:
                data = f.read()
            if len(data) < 100:
                return ''
            b64 = base64.b64encode(data).decode('ascii')
            return f'data:image/jpeg;base64,{b64}'
        except Exception:
            return ''
        finally:
            os.unlink(tmp.name)

    # ── Preview ─────────────────────────────────────────────

    def preview_video(self, file_path: str) -> dict:
        """Open a video file in the system default player."""
        import subprocess
        p = Path(file_path)
        if not p.exists():
            return {"success": False, "error": f"文件不存在: {file_path}"}
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(p)])
            elif sys.platform == "win32":
                subprocess.Popen(["start", "", str(p)], shell=True)
            else:
                subprocess.Popen(["xdg-open", str(p)])
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_output_files(self, video_path: str) -> list[dict]:
        """Get list of output files for a processed video from cache/disk."""
        vpath = Path(video_path)
        config_output = ""
        try:
            from core.user_settings import build_config_from_settings
            c = build_config_from_settings()
            config_output = c.output_dir
        except Exception:
            pass
        base_output = Path(config_output) if config_output else vpath.parent / "output"
        stem = vpath.stem
        # Look in per-video subfolder first, fall back to flat directory
        video_dir = base_output / stem
        search_dir = video_dir if video_dir.exists() else base_output
        results = []
        if search_dir.exists():
            for f in sorted(search_dir.glob(f"{stem}_v*")):
                results.append({
                    "path": str(f),
                    "name": f.name,
                    "size_mb": round(f.stat().st_size / 1024 / 1024, 1),
                })
        return results


def main():
    if not _DIST_DIR.exists():
        logger.error("Web UI not built. Run: npm --prefix webui run build")
        sys.exit(1)

    api = PythonBridge()
    window = webview.create_window(
        title="CutPilot — AI 副驾驶",
        url=str(_DIST_DIR / "index.html"),
        js_api=api,
        width=1280,
        height=820,
        min_size=(1000, 600),
        background_color="#f8f9fa",
    )

    def on_loaded():
        api.set_window(window)
        # Check license and warn if expired
        try:
            from core.license import check_license, get_trial_remaining
            is_valid, message, expiry = check_license()
            trial = get_trial_remaining()
            if not is_valid and trial <= 0:
                js = 'window.dispatchEvent(new CustomEvent("license-warning", {detail: {message: "授权已过期且试用次数已用完，请联系管理员获取激活码", level: "error"}}))'
                window.evaluate_js(js)
            elif not is_valid:
                js = f'window.dispatchEvent(new CustomEvent("license-warning", {{detail: {{message: "试用模式: 剩余 {trial} 次免费使用", level: "info"}}}}))'
                window.evaluate_js(js)
            elif expiry:
                from datetime import date, timedelta
                if expiry - date.today() < timedelta(days=7):
                    days_left = (expiry - date.today()).days
                    js = f'window.dispatchEvent(new CustomEvent("license-warning", {{detail: {{message: "授权将在 {days_left} 天后到期，请及时续费", level: "info"}}}}))'
                    window.evaluate_js(js)
        except Exception:
            pass

    window.events.loaded += on_loaded
    webview.start(debug=("--debug" in sys.argv))


if __name__ == "__main__":
    main()
