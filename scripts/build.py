#!/usr/bin/env python3
"""CutPilot build script — encrypt + package for distribution.

Usage:
    python scripts/build.py          # Build for current platform
    python scripts/build.py --skip-encrypt  # Skip PyArmor (dev builds)

Produces:
    macOS:   dist/CutPilot.app
    Windows: dist/CutPilot/CutPilot.exe
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE_DIR = ROOT / "core"
BUILD_DIR = ROOT / "build"
DIST_DIR = ROOT / "dist"
WEBUI_DIST = ROOT / "webui" / "dist"


def run(cmd: list[str], **kwargs) -> None:
    print(f"  $ {' '.join(cmd)}")
    subprocess.check_call(cmd, **kwargs)


def step(msg: str) -> None:
    print(f"\n{'='*50}")
    print(f"  {msg}")
    print(f"{'='*50}\n")


def build_frontend() -> None:
    step("构建前端")
    if WEBUI_DIST.exists() and any(WEBUI_DIST.iterdir()):
        print("  webui/dist 已存在，跳过构建")
        return
    run(["npm", "install", "--silent"], cwd=str(ROOT / "webui"))
    run(["npm", "run", "build"], cwd=str(ROOT / "webui"))


def encrypt_core(skip: bool = False) -> Path:
    """Encrypt core/ with PyArmor. Returns path to encrypted core dir."""
    step("加密核心代码")
    if skip:
        print("  跳过加密（开发模式）")
        return CORE_DIR

    encrypted_dir = BUILD_DIR / "core_encrypted"
    if encrypted_dir.exists():
        shutil.rmtree(encrypted_dir)

    # PyArmor encrypt
    run([
        sys.executable, "-m", "pyarmor", "gen",
        "--output", str(encrypted_dir),
        "--platform", "auto",
        str(CORE_DIR),
    ])

    return encrypted_dir


def build_pyinstaller(encrypted_core: Path) -> None:
    step("PyInstaller 打包")

    is_mac = platform.system() == "Darwin"
    is_win = platform.system() == "Windows"

    # Clean old build
    for d in [BUILD_DIR / "CutPilot", DIST_DIR / "CutPilot", DIST_DIR / "CutPilot.app"]:
        if d.exists():
            shutil.rmtree(d)

    # Build datas list
    datas = [
        (str(WEBUI_DIST), "webui/dist"),
        (str(ROOT / "config" / "prompts"), "config/prompts"),
    ]
    sensitive_words = ROOT / "config" / "sensitive_words.json"
    if sensitive_words.exists():
        datas.append((str(sensitive_words), "config"))

    # If encrypted, use encrypted core instead of original
    if encrypted_core != CORE_DIR:
        datas.append((str(encrypted_core), "core"))

    # Build command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "CutPilot",
        "--noconfirm",
        "--clean",
        "--windowed",  # No console window
    ]

    for src, dst in datas:
        cmd.extend(["--add-data", f"{src}{os.pathsep}{dst}"])

    # Hidden imports
    hidden = [
        "webview", "bottle",
        "openai", "httpx", "httpcore",
        "pydantic", "pydantic_settings",
        "PIL",
    ]
    for h in hidden:
        cmd.extend(["--hidden-import", h])

    # Excludes (reduce size)
    excludes = ["matplotlib", "IPython", "jupyter", "tkinter", "PySide6", "PyQt5"]
    for e in excludes:
        cmd.extend(["--exclude-module", e])

    if is_mac:
        cmd.extend([
            "--osx-bundle-identifier", "com.cutpilot.app",
        ])

    cmd.append(str(ROOT / "main_webui.py"))

    run(cmd, cwd=str(ROOT))


def post_build() -> None:
    step("打包完成")
    is_mac = platform.system() == "Darwin"

    if is_mac:
        app_path = DIST_DIR / "CutPilot.app"
        if app_path.exists():
            # Create DMG-ready zip
            zip_name = f"CutPilot-mac-{platform.machine()}"
            shutil.make_archive(str(DIST_DIR / zip_name), "zip", str(DIST_DIR), "CutPilot.app")
            print(f"  macOS 包: dist/{zip_name}.zip")
            print(f"  直接运行: open dist/CutPilot.app")
    else:
        exe_dir = DIST_DIR / "CutPilot"
        if exe_dir.exists():
            zip_name = "CutPilot-windows-x64"
            shutil.make_archive(str(DIST_DIR / zip_name), "zip", str(DIST_DIR), "CutPilot")
            print(f"  Windows 包: dist/{zip_name}.zip")
            print(f"  直接运行: dist\\CutPilot\\CutPilot.exe")


def main() -> None:
    skip_encrypt = "--skip-encrypt" in sys.argv

    print(f"\n  CutPilot Build ({platform.system()} {platform.machine()})")
    print(f"  加密: {'跳过' if skip_encrypt else 'PyArmor'}\n")

    build_frontend()
    encrypted = encrypt_core(skip=skip_encrypt)
    build_pyinstaller(encrypted)
    post_build()


if __name__ == "__main__":
    main()
