# -*- mode: python ; coding: utf-8 -*-
# Сборка Auraloom Voice Studio для Manual QA в ONEDIR режиме.
#
#   pyinstaller --clean --noconfirm auraloom_qa.spec
#
# Выход: release/ManualQA/Auraloom.exe (ONEFILE EXE)
#        release/ManualQA/Auraloom_Data/ (все зависимости)
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

# Выходная папка для релиза Manual QA
qa_dist = os.path.join(ROOT, "release", "ManualQA")
print(">>> QA DIST =", qa_dist)

datas = []
for src, dest in (
    (os.path.join(ROOT, "lines.json"), "."),
    (os.path.join(ROOT, "player"), "player"),
    (os.path.join(ROOT, "voices"), "voices"),
    (os.path.join(ROOT, "tools"), "tools"),
    # VBCable installers НЕ входят в поставку по лицензии.
    # Пользователь устанавливает виртуальный кабель отдельно по мануалу
    # при необходимости (запасной вариант для захвата аудио).
    # (os.path.join(ROOT, "installers"), "installers"),
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

# Включаем UI-модули (Liquid Glass)
ui_src = os.path.join(ROOT, "app", "ui")
if os.path.isdir(ui_src):
    for dirpath, dirnames, filenames in os.walk(ui_src):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, ROOT)
            dest_dir = os.path.dirname(rel)
            datas.append((full, dest_dir))
    print(">>> data: app/ui -> app/ui")

entry = os.path.join(ROOT, "app", "voice_studio.py")
if not os.path.exists(entry):
    entry = os.path.join(SPECPATH, "voice_studio.py")
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
    "incoming_tts",          # P1: IncomingTTSProvider
    "western_style",         # Этап B: Western Style Engine
    "voice_prompts",         # C.7.8: звуковые подсказки для записи голоса
    "prompt_library",        # готовые референсы интонации (voices/prompts)
    "ui.voices",             # новая вкладка «Голоса» (3 под-вкладки)
    "ui.audio_play",         # воспроизведение и сравнение образцов
    "sounddevice",
    "soundfile",
    "numpy",
    "tkinter",
    "tkinter.ttk",
    "pyaudiowpatch",         # Этап A1: WASAPI Endpoint Loopback
    # Piper — для озвучки подсказок (эмоции). Без него «Как сказать»
    # не работает в EXE.
    "piper",
    "piper.voice",
    "piper.config",
    "piper.phonemize_espeak",
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
        # Копируем только __init__.py (__main__.py обрабатывается PyInstaller отдельно)
        init_py = os.path.join(pyaudiowpatch_dir, "__init__.py")
        if os.path.isfile(init_py):
            datas.append((init_py, "pyaudiowpatch"))
            print(">>> data: pyaudiowpatch/__init__.py -> pyaudiowpatch")
except ImportError:
    print(">>> WARNING: pyaudiowpatch not installed, WASAPI Loopback will not work in frozen EXE")

# Включаем пакет piper (озвучка подсказок с интонацией).
# Без него кнопка «▶ Как сказать» в EXE пишет «Piper недоступен».
try:
    import piper
    piper_dir = os.path.dirname(piper.__file__)
    if piper_dir and os.path.isdir(piper_dir):
        for dirpath, dirnames, filenames in os.walk(piper_dir):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for fn in filenames:
                if fn.endswith((".py", ".json", ".txt", ".onnx")):
                    full = os.path.join(dirpath, fn)
                    rel = os.path.relpath(full, piper_dir)
                    dest_dir = os.path.join("piper", os.path.dirname(rel))
                    datas.append((full, dest_dir))
        print(">>> data: piper -> piper")
except ImportError:
    print(">>> WARNING: piper not installed, подсказки работать не будут")

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
    name="Auraloom",
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
    name="Auraloom",
)
