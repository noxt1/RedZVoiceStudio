# -*- mode: python ; coding: utf-8 -*-
# Сборка RedZ Voice Studio в один EXE.
#
#   pyinstaller --clean --noconfirm redz_voice_studio.spec
#
# В бандл входят: GUI, лёгкие зависимости (numpy/soundfile/sounddevice),
# голоса Piper es-MX, lines.json, плеер и CLI-инструменты (tools/).
# Тяжёлый движок (torch + coqui-tts) в бандл НЕ входит — он живёт рядом
# в %LOCALAPPDATA%\RedZVoiceStudio\engine и ставится один раз.

import os

from PyInstaller.utils.hooks import collect_data_files

# SPECPATH = папка spec-файла (app/). Корень проекта — уровнем выше.
# PyInstaller меняет cwd, поэтому полагаемся только на SPECPATH.
ROOT = os.path.abspath(os.path.dirname(SPECPATH))
if not os.path.exists(os.path.join(ROOT, "lines.json")):
    ROOT = os.path.abspath(os.getcwd())
print(">>> ROOT =", ROOT)

datas = []
for src, dest in (
    (os.path.join(ROOT, "lines.json"), "."),
    (os.path.join(ROOT, "player"), "player"),
    (os.path.join(ROOT, "voices"), "voices"),
    (os.path.join(ROOT, "tools"), "tools"),
    (os.path.join(ROOT, "installers"), "installers"),
    # файлы ресурса для установки на сервер RedZ/FiveM
    (os.path.join(ROOT, "fxmanifest.lua"), "."),
    (os.path.join(ROOT, "client.lua"), "."),
    (os.path.join(ROOT, "keybinds.lua"), "."),
    (os.path.join(ROOT, "server.lua"), "."),
    (os.path.join(ROOT, "config.lua"), "."),
    (os.path.join(ROOT, "html"), "html"),
):
    if os.path.exists(src):
        if os.path.isdir(src):
            # берём только файлы, без __pycache__
            #
            # ВАЖНО: в PyInstaller `datas` — это пары (файл, ПАПКА_НАЗНАЧЕНИЕ),
            # а НЕ (файл, полный_путь). Если указать "tools/live_translate.py",
            # PyInstaller создаст КАТАЛОГ с таким именем и положит файл внутрь.
            # Поэтому назначение — папка, а полное имя файла задаёт basename.
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
    "sounddevice",
    "soundfile",
    "numpy",
    "tkinter",
    "tkinter.ttk",
]

# espeak-данные нужны Piper, если он запускается из движка
try:
    import piper_phonemize  # noqa: F401
    datas += collect_data_files("piper_phonemize")
except Exception:
    pass

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
    name="RedZVoiceStudio",
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
