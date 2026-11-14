"""Виртуальный аудиокабель (VB-CABLE): скачать, установить, найти.

Зачем: чтобы «живой перевод» (и реплики) слышали другие, приложение должно
играть в устройство, которое у них стоит микрофоном. В системе такого
устройства нет, а встроенный «Стерео микшер» игра (RedM/Mumble) в списке
микрофонов не показывает.

Схема с кабелем:
    приложение -> «CABLE Input» (воспроизведение)
                -> «CABLE Output» (запись) -> его выбирают микрофоном в игре

Почему не просто открыть сайт: vb-audio.com с машины пользователя
недоступен (TLS timeout), поэтому установщик берём с доступных зеркал
(GitHub) и кладём в workspace\\installers.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

APP_NAME = "RedZVoiceStudio"
UA = {"User-Agent": f"{APP_NAME}/1.0"}

# Зеркала полного пакета VB-CABLE Driver Pack 45 (официальный установщик).
# Первое — официальный, остальные — резервные (vb-audio.com может быть недоступен).
MIRRORS = [
    "https://raw.githubusercontent.com/spdore/wanxiang-bgm/HEAD/vendor/vb-cable/"
    "VBCABLE_Driver_Pack45.zip",
    "https://raw.githubusercontent.com/AlekseyMartynov/action-vbcable-win/HEAD/"
    "VBCABLE_Driver_Pack45.zip",
]

ZIP_NAME = "VBCABLE_Driver_Pack45.zip"
SETUP_X64 = "VBCABLE_Setup_x64.exe"
SETUP_X86 = "VBCABLE_Setup.exe"


def _local_app_data() -> str:
    return os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")


def workspace_dir() -> str:
    """Рабочая папка приложения (как в studio_paths)."""
    return os.path.join(_local_app_data(), APP_NAME, "workspace")


def installers_dir() -> str:
    """Папка, куда кладём установщик (в рабочей папке)."""
    path = os.path.join(workspace_dir(), "installers")
    os.makedirs(path, exist_ok=True)
    return path


def search_dirs() -> list[str]:
    """Где искать установщик: рабочая папка, папка рядом с EXE, бандл."""
    dirs = [installers_dir()]
    try:
        import studio_paths as sp
        dirs.append(os.path.join(sp.app_dir(), "installers"))
        dirs.append(os.path.join(sp.resource_dir(), "installers"))
    except Exception:
        pass
    return [d for d in dirs if os.path.isdir(d)]


def zip_path() -> str:
    return os.path.join(installers_dir(), ZIP_NAME)


def setup_path() -> str | None:
    """Путь к установщику (если пакет уже распакован или лежит рядом)."""
    for name in (SETUP_X64, SETUP_X86):
        for base in search_dirs():
            for root, _dirs, files in os.walk(base):
                if name in files:
                    return os.path.join(root, name)
    return None


def download(progress=None) -> tuple[bool, str]:
    """Скачать пакет установщика. (ок, сообщение)."""
    dst = zip_path()
    if os.path.exists(dst) and os.path.getsize(dst) > 200_000:
        return True, f"установщик уже скачан: {dst}"
    last = ""
    for url in MIRRORS:
        try:
            if progress:
                progress(f"качаю с {url.split('/')[2]}…")
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = resp.read()
            if len(data) < 50_000:
                last = "файл слишком мал — это не тот пакет"
                continue
            with open(dst, "wb") as fh:
                fh.write(data)
            _extract(dst)
            if progress:
                progress(f"скачано: {len(data) // 1024} КБ")
            return True, f"установщик скачан: {dst}"
        except Exception as exc:  # noqa: BLE001
            last = f"{type(exc).__name__}: {exc}"
            continue
    return False, (f"не скачалось: {last}" if last else "нет доступных зеркал")


def _extract(zip_file: str) -> None:
    """Распаковать пакет (установщик лежит во вложенной папке)."""
    try:
        with zipfile.ZipFile(zip_file) as z:
            z.extractall(installers_dir())
    except Exception:
        pass


def is_installed() -> bool:
    """Есть ли в системе устройства кабеля."""
    return bool(cable_devices())


def cable_devices() -> dict:
    """Найти устройства кабеля: {'input': (idx, name), 'output': (idx, name)}."""
    out: dict = {}
    try:
        import sounddevice as sd
        for i, d in enumerate(sd.query_devices()):
            name = d["name"]
            low = name.lower()
            if not any(k in low for k in ("cable", "vb-audio", "vbcable")):
                continue
            if d["max_input_channels"] > 0 and "input" not in out:
                out["input"] = (i, name)
            if d["max_output_channels"] > 0 and "output" not in out:
                out["output"] = (i, name)
    except Exception:
        pass
    return out


def run_installer() -> tuple[bool, str]:
    """Запустить установщик с правами администратора."""
    setup = setup_path()
    if not setup:
        ok, msg = download()
        if not ok:
            return False, msg
        setup = setup_path()
        if not setup:
            return False, "установщик не найден после скачивания"
    try:
        # ShellExecute с runas -> запрос прав администратора (UAC)
        import ctypes
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", setup, None, os.path.dirname(setup), 1)
        return True, "открыл установщик: нажми «Install Driver», потом «OK»"
    except Exception as exc:  # noqa: BLE001
        # запасной путь: просто запустить (без повышения прав)
        try:
            subprocess.Popen([setup], cwd=os.path.dirname(setup))
            return True, ("запустил установщик. Если попросит права — "
                          "разреши, потом нажми Install Driver")
        except Exception as exc2:  # noqa: BLE001
            return False, f"не запустился: {exc} / {exc2}"


def uninstall_hint() -> str:
    return ("Панель управления VB-CABLE: «Установить VoiceMeeter» или "
            "CABLE Control Panel -> Uninstall Driver")
