# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['main_webui.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('webui/dist', 'webui/dist'),
        ('config/prompts', 'config/prompts'),
        ('config/sensitive_words.json', 'config'),
    ],
    hiddenimports=[
        'webview', 'bottle',
        'funasr', 'torch', 'openai', 'httpx',
        'pydantic', 'pydantic_settings',
        'moviepy', 'PIL',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'IPython', 'jupyter', 'tkinter', 'PySide6'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='CutPilot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='CutPilot',
)
app = BUNDLE(
    coll,
    name='CutPilot.app',
    icon=None,
    bundle_identifier='com.cutpilot.app',
)
