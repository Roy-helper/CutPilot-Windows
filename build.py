"""CutPilot build script — PyInstaller packaging.

Usage:
    python build.py          # Build for current platform
    python build.py --clean  # Remove dist/ and build/ before building

The script uses --onedir mode (a directory with the executable + dependencies).
For a single-file binary, change --onedir to --onefile (slower startup, larger).
"""
from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

# Platform-specific path separator for --add-data
_SEP = ";" if platform.system() == "Windows" else ":"


def _add_data(src: str, dest: str) -> list[str]:
    """Return --add-data flag with platform-correct separator."""
    return ["--add-data", f"{src}{_SEP}{dest}"]


def _build_command() -> list[str]:
    """Assemble the PyInstaller command for the current platform."""
    cmd: list[str] = [
        sys.executable, "-m", "PyInstaller",
        "--name", "CutPilot",
        "--onedir",
        "--windowed",
        "--noconfirm",
        # ── Data files ──────────────────────────────────────────
        *_add_data("config/prompts", "config/prompts"),
        *_add_data("config/sensitive_words.json", "config"),
        # ── Hidden imports PyInstaller misses ────────────────────
        "--hidden-import", "PySide6.QtSvg",
        "--hidden-import", "PySide6.QtSvgWidgets",
        "--hidden-import", "funasr",
        "--hidden-import", "torch",
        "--hidden-import", "modelscope",
        "--hidden-import", "openai",
        "--hidden-import", "httpx",
        "--hidden-import", "pydantic",
        "--hidden-import", "pydantic_settings",
        "--hidden-import", "imageio_ffmpeg",
        # ── Exclude unnecessary large modules to reduce size ─────
        "--exclude-module", "matplotlib",
        "--exclude-module", "scipy.spatial",
        "--exclude-module", "IPython",
        "--exclude-module", "jupyter",
        "--exclude-module", "notebook",
        "--exclude-module", "tkinter",
    ]

    system = platform.system()
    if system == "Darwin":
        cmd.extend(["--osx-bundle-identifier", "com.cutpilot.app"])
        icon_path = PROJECT_ROOT / "assets" / "icon.icns"
        if icon_path.exists():
            cmd.extend(["--icon", str(icon_path)])
    elif system == "Windows":
        icon_path = PROJECT_ROOT / "assets" / "icon.ico"
        if icon_path.exists():
            cmd.extend(["--icon", str(icon_path)])

    cmd.append("main.py")
    return cmd


def _clean() -> None:
    """Remove build artifacts."""
    for dirname in ("build", "dist"):
        target = PROJECT_ROOT / dirname
        if target.exists():
            print(f"Removing {target}")
            shutil.rmtree(target)
    spec_file = PROJECT_ROOT / "CutPilot.spec"
    if spec_file.exists():
        print(f"Removing {spec_file}")
        spec_file.unlink()


def build(*, clean: bool = False) -> None:
    """Run the PyInstaller build."""
    if clean:
        _clean()

    cmd = _build_command()
    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True, cwd=str(PROJECT_ROOT))

    print("\nBuild complete. Output in dist/CutPilot/")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Build CutPilot with PyInstaller")
    parser.add_argument(
        "--clean", action="store_true",
        help="Remove build/ and dist/ before building",
    )
    args = parser.parse_args()
    build(clean=args.clean)


if __name__ == "__main__":
    main()
