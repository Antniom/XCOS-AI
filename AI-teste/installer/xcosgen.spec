# -*- mode: python ; coding: utf-8 -*-
# xcosgen.spec — PyInstaller build spec for XcosGen
#
# Usage (from project root):
#   pyinstaller installer/xcosgen.spec
#
# Output: dist/XcosGen/XcosGen.exe  (one-directory build)

import sys
import os

block_cipher = None

# ── Data files to bundle ───────────────────────────────────────────────────
added_files = [
    # Include the entire ui/ folder so index.html + app.js are resolved
    ('ui',  'ui'),
]

# ── Collect hidden pywebview imports (platform-specific) ──────────────────
hidden_imports = [
    'webview.platforms.winforms',  # Windows WebView2 backend
    'clr',                          # pythonnet (used by pywebview on Windows)
    'appdirs',
    'google.genai',
    'google.auth',
    'google.auth.transport',
    'pdfminer',
    'pdfminer.high_level',
    'pdfminer.layout',
    'PIL',
    'PIL.Image',
    'tkinter',
    'tkinter.filedialog',
]

a = Analysis(
    ['../main.py'],
    pathex=[os.path.abspath('..')],
    binaries=[],
    datas=added_files,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='XcosGen',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,         # Windows GUI app — no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,             # Replace with path to .ico when available
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='XcosGen',
)
