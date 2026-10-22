# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


project_dir = Path(SPECPATH)
static_dir = project_dir / "drcrawler" / "static"

a = Analysis(
    [str(project_dir / "run_drcrawler.py")],
    pathex=[str(project_dir)],
    binaries=[],
    datas=[(str(static_dir), "drcrawler/static")],
    hiddenimports=[
        "drcrawler.database",
        "drcrawler.downloads",
        "tkinter",
        "tkinter.filedialog",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="DRCrawler",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
