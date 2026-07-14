# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Revona CLI — standalone binary with zero Python deps."""

import platform
from pathlib import Path

APP_NAME = "revona"
PROJECT_ROOT = Path(SPECPATH).parent
ENTRY_POINT = str(PROJECT_ROOT / "revona_main.py")

# Detect platform for naming
OS = platform.system().lower()
ARCH = platform.machine().lower()
PLATFORM_TAG = f"{OS}_{ARCH}"

# Collect data files: Skills, Blueprints, Accelerators, AI, .user
DATAS = []
for data_dir in ("Skills", "Blueprints", "Accelerators", "AI", ".user"):
    p = PROJECT_ROOT / data_dir
    if p.is_dir():
        DATAS.append((str(p), data_dir))

a = Analysis(
    [ENTRY_POINT],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=DATAS,
    hiddenimports=[
        "agent",
        "agent.cli",
        "agent.agent",
        "agent.agents",
        "agent.mission",
        "agent.memory",
        "agent.skills",
        "agent.repo_intel",
        "agent.tui",
        "agent.progress",
        "agent.prompts",
        "agent.terminal",
        "agent.client",
        "agent.config",
        "agent.context",
        "agent.session",
        "agent.models",
        "click",
        "rich",
        "rich.markdown",
        "rich.syntax",
        "rich.table",
        "rich.progress",
        "rich.layout",
        "rich.live",
        "rich.panel",
        "rich.columns",
        "rich.text",
        "rich.tree",
        "rich.prompt",
        "requests",
        "openai",
        "httpx",
        "tiktoken",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "numpy",
        "pandas",
        "scipy",
        "PIL",
        "cv2",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        "notebook",
        "jupyter",
        "ipykernel",
        "IPython",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    contents_directory=".",
    # Bundle metadata
    version_file=None,
)
