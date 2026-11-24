# -*- mode: python ; coding: utf-8 -*-
# Сборка Auraloom Voice Studio LEGACY (старый интерфейс) в ONEDIR режиме.
#
#   pyinstaller --clean --noconfirm auraloom_legacy.spec
#
# Выход: release/ManualQA/Auraloom_Legacy.exe (ONEDIR EXE)
#        release/ManualQA/Auraloom_Data/ (общая папка зависимостей с основным EXE)
#
# Legacy EXE запускает старый интерфейс (6 вкладок) автоматически через
# app/legacy_entry.py (режим --ui-old). Все компоненты — те же, что и в
# основном EXE: Studio, LiveTab, LiveClient, MicBridge, GlobalHotkeys,
# Engine, модели, настройки, голосовые профили, пользовательские данные.
#
# Тяжёлый движок (torch + coqui-tts + faster-whisper + transformers)
# в бандл НЕ входит — он живёт рядом в %LOCALAPPDATA%\Auraloom\engine
# и ставится отдельно (tools/setup_env.ps1).

import os
import sys

from PyInstaller.utils.hooks import collect_data_files

# SPECPATH = папка spec-файла (app/). Корень проекта — уровнем выше.
ROOT = os.path.abspath(os.path.dirname(SPECPATH))
if not os.path.exists(os.path.join(ROOT, "lines.json")):
    ROOT = os.path.abspath(os.getcwd())
print(">>> ROOT =", ROOT)

# Выходная папка для релиза Manual QA (та же, что у основного EXE)
qa_dist = os.path.join(ROOT, "release", "ManualQA")
print(">>> QA DIST =", qa_dist)

datas = []
for src, dest in (
    (os.path.join(ROOT, "lines.json"), "."),
    (os.path.join(ROOT, "player"), "player"),
    (os.path.join(ROOT, "voices"), "voices"),
    (os.path.join(ROOT, "tools"), "tools"),
    (os.path.join(ROOT, "installers"), "installers"),
    (os.path.join(ROOT, "fxmanifest.lua"), "."),
    (os.path.join(ROOT, "client.lua"), "."),
    (os.path.join(ROOT, "keybinds.lua"), "."),
    (os.path.join(ROOT, "server.lua"), "."),
    (os.path.join(ROOT, "config.lua"), "."),
    (os.path.join(ROOT, "html"), "html"),
):
    if os.path.exists(src):
        if os.path.isdir(src):
            files = []
            for dirpath, dirnames, filenames in os.walk(src):
                dirnames[:] = [d for d in dirnames if d != "__pycache__"]
                for fn in filenames:
                    full = os.path.join(dirpath, fn)
                    rel = os.path.relpath(full, src)
                    sub = os.path.dirname(rel)
                    dest_dir = os.path.join(dest, sub) if sub else dest
                    files.append((full, dest_dir))
            datas += files
        else:
            datas.append((src, dest))
        print(">>> data:", src, "->", dest)
    else:
        print(">>> MISSING:", src)

# Включаем app/ (включая legacy_entry.py и все модули старого UI)
app_src = os.path.join(ROOT, "app")
if os.path.isdir(app_src):
    for dirpath, dirnames, filenames in os.walk(app_src):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, ROOT)
            dest_dir = os.path.dirname(rel)
            datas.append((full, dest_dir))
    print(">>> data: app -> app")

entry = os.path.join(ROOT, "app", "legacy_entry.py")
print(">>> entry:", entry)

hiddenimports = [
    "studio_core",
    "studio_paths",
    "hotkeys",
    "translate",
    "live_tab",
    "live_client",
    "logpanel",
    "mic_bridge",
    "scrollframe",
    "cable",
    "incoming_tts",
    "sounddevice",
    "soundfile",
    "numpy",
    "tkinter",
    "tkinter.ttk",
    "pyaudiowpatch",
]

# espeak-данные нужны Piper, если он запускается из движка
try:
    import piper_phonemize  # noqa: F401
    datas += collect_data_files("piper_phonemize")
except Exception:
    pass

# Включаем PyAudioWPatch пакет (WASAPI Endpoint Loopback)
try:
    import pyaudiowpatch
    pyaudiowpatch_dir = os.path.dirname(pyaudiowpatch.__file__)
    if pyaudiowpatch_dir and os.path.isdir(pyaudiowpatch_dir):
        init_py = os.path.join(pyaudiowpatch_dir, "__init__.py")
        if os.path.isfile(init_py):
            datas.append((init_py, "pyaudiowpatch"))
            print(">>> data: pyaudiowpatch/__init__.py -> pyaudiowpatch")
except ImportError:
    print(">>> WARNING: pyaudiowpatch not installed, WASAPI Loopback will not work in frozen EXE")

a = Analysis(
    [entry],
    pathex=[os.path.join(ROOT, "app"), os.path.join(ROOT, "tools"), SPECPATH],
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
    name="Auraloom_Legacy",
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

# Коллекция для ONEDIR: EXE + все файлы в одной папке Auraloom_Data/
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="Auraloom_Legacy",
)
