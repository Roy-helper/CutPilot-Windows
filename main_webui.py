"""CutPilot — Web UI launcher via pywebview.

Opens a native window rendering the Vue 3 + Ant Design frontend.
Python backend functions are exposed to JavaScript via the pywebview API bridge.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import webview

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Path to the built Vue app
_DIST_DIR = Path(__file__).parent / "webui" / "dist"


class PythonBridge:
    """API bridge exposed to JavaScript as `window.pywebview.api`.

    Every public method here is callable from the Vue frontend.
    This is the skeleton — methods will be connected to core/ modules.
    """

    def get_machine_id(self) -> str:
        from core.license import get_machine_id
        return get_machine_id()

    def get_license_info(self) -> dict:
        from core.license import get_license_info
        return get_license_info()

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

    def get_providers(self) -> list[dict]:
        from core.providers import PROVIDERS
        return [p.model_dump() for p in PROVIDERS]

    def ping(self) -> str:
        """Health check — verify bridge is working."""
        return "pong"


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
        background_color="#141421",
    )
    webview.start(debug=("--debug" in sys.argv))


if __name__ == "__main__":
    main()
