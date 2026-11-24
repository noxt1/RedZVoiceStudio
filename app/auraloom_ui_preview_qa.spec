# -*- mode: python ; coding: utf-8 -*-
# Сборка Auraloom UIPreview (прототип Liquid Glass) для Manual QA.
#
#   pyinstaller --clean --noconfirm --distpath dist/ManualQA auraloom_ui_preview_qa.spec
#
# Выход: dist/ManualQA/AuraloomUIPreview.exe

import os
import sys

ROOT = os.path.abspath(os.path.dirname(SPECPATH))
if not os.path.exists(os.path.join(ROOT, "lines.json")):
    ROOT = os.path.abspath(os.getcwd())

datas = []
# Включаем UI-модули
ui_src = os.path.join(ROOT, "app", "ui")
if os.path.isdir(ui_src):
    for dirpath, dirnames, filenames in os.walk(ui_src):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, ROOT)
            dest_dir = os.path.dirname(rel)
            datas.append((full, dest_dir))

entry = os.path.join(ROOT, "app", "ui", "proto_main.py")
print(">>> UI Preview entry:", entry)

hiddenimports = [
    "sounddevice",
    "soundfile",
    "numpy",
    "tkinter",
    "tkinter.ttk",
]

a = Analysis(
    [entry],
    pathex=[os.path.join(ROOT, "app"), SPECPATH],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["torch", "torchaudio", "TTS", "coqui_tts", "speechbrain",
              "faster_whisper", "transformers", "onnxruntime", "matplotlib",
              "IPython", "pytest", "scipy", "librosa", "numba", "llvmlite"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="AuraloomUIPreview",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(ROOT, "app", "studio.ico") if os.path.exists(
        os.path.join(ROOT, "app", "studio.ico")) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="AuraloomUIPreview",
)
