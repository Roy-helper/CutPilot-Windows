"""Window management for CutPilot — pywebview native + Bottle fallback.

Handles native window creation, .NET detection on Windows, FFmpeg check,
and the Bottle HTTP fallback for environments without .NET Framework.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import webview

from core.bridge_api import PythonBridge

logger = logging.getLogger(__name__)

_DIST_DIR = Path(__file__).parent.parent / "webui" / "dist"


def start_bottle_server(api: PythonBridge, port: int = 18989) -> None:
    """Fallback: serve the Vue app via Bottle + expose API as JSON endpoints.

    Used when pywebview cannot initialize (missing .NET Framework).
    Opens the UI in the system default browser.
    """
    import webbrowser
    from bottle import Bottle, static_file, request, response

    app = Bottle()

    # Serve static files
    @app.route("/")
    def serve_index():
        return static_file("index.html", root=str(_DIST_DIR))

    @app.route("/assets/<filepath:path>")
    def serve_assets(filepath):
        return static_file(filepath, root=str(_DIST_DIR / "assets"))

    @app.route("/<filepath:path>")
    def serve_static(filepath):
        return static_file(filepath, root=str(_DIST_DIR))

    # JSON-RPC style bridge: POST /api/<method_name>
    @app.route("/api/<method_name>", method="POST")
    def api_call(method_name):
        response.content_type = "application/json"
        method = getattr(api, method_name, None)
        if method is None:
            return json.dumps({"error": f"Unknown method: {method_name}"})
        try:
            body = request.json or {}
            args = body.get("args", [])
            kwargs = body.get("kwargs", {})
            result = method(*args, **kwargs)
            return json.dumps(result, default=str, ensure_ascii=False)
        except Exception as e:
            logger.exception("API call failed: %s", method_name)
            return json.dumps({"error": str(e)})

    logger.info("Starting fallback Bottle server on http://localhost:%d", port)
    webbrowser.open(f"http://localhost:{port}")
    app.run(host="localhost", port=port, quiet=True)


def check_ffmpeg() -> bool:
    """Check if ffmpeg is available in PATH. Show dialog if missing."""
    import subprocess as _sp
    try:
        _sp.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        return True
    except FileNotFoundError:
        logger.error("FFmpeg not found in PATH")
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(
                    0,
                    "未检测到 FFmpeg，CutPilot 需要 FFmpeg 才能处理视频。\n\n"
                    "请下载安装后重启：\n"
                    "https://www.gyan.dev/ffmpeg/builds/\n\n"
                    "下载 ffmpeg-release-essentials.zip，解压后将 bin 目录\n"
                    "添加到系统 PATH 环境变量。",
                    "CutPilot — 缺少 FFmpeg",
                    0x00000010,  # MB_ICONERROR
                )
            except Exception:
                pass
        return False
    except Exception:
        return True  # ffmpeg exists but some other error, let it pass


def main(log_file: Path | None = None) -> None:
    """Application entry point — create window and start the event loop."""
    if not _DIST_DIR.exists():
        logger.error("Web UI not built. Run: npm --prefix webui run build")
        sys.exit(1)

    if not check_ffmpeg():
        sys.exit(1)

    api = PythonBridge(log_file=log_file)

    # Check if pywebview/.NET is available on Windows
    _use_native_window = True
    if sys.platform == "win32":
        try:
            import clr  # noqa: F401 — triggers pythonnet/.NET check
        except Exception:
            _use_native_window = False
            logger.warning(".NET Framework not available — will use browser mode")
            # Show a dialog telling user what's happening
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(
                    0,
                    "检测到您的电脑缺少 .NET Framework 运行环境。\n\n"
                    "CutPilot 将自动使用浏览器模式运行（功能完全相同）。\n\n"
                    "如需使用独立窗口模式，请安装 .NET Framework 4.8：\n"
                    "https://dotnet.microsoft.com/download/dotnet-framework/net48\n\n"
                    "点击「确定」继续启动...",
                    "CutPilot — 环境提示",
                    0x00000040,  # MB_ICONINFORMATION
                )
            except Exception:
                pass

    if not _use_native_window:
        start_bottle_server(api)
        return

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

    try:
        webview.start(debug=("--debug" in sys.argv))
    except Exception:
        logger.warning("pywebview failed to start, falling back to browser mode")
        start_bottle_server(api)
