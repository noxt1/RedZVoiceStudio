"""End-to-end проверка хоткеев в СОБРАННОМ EXE.

Проверяет два сценария:
  1. дефолтные комбинации (Ctrl+Alt+...) — РЕГИСТРИРУЮТСЯ все три;
  2. одиночная клавиша — РЕАЛЬНО срабатывает (настоящее нажатие).

Сценарий 2 проверяется с временной подменой настроек: пишем
live_hotkeys.json с одиночными клавишами (F9/F10/F11) — иначе
синтетический ввод не доставит комбинацию с модификаторами
(ограничение Windows, а не баг приложения).

    python tools\\test_hotkey_e2e.py
"""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

import studio_paths as sp  # noqa: E402

EXE = os.path.join(ROOT, "dist", "RedZVoiceStudio.exe")
LOG_NAME = "hotkey_events.log"
HOTKEY_FILE = "live_hotkeys.json"

KEYEVENTF_KEYUP = 0x0002
# одиночные клавиши для проверки срабатывания
TEST_KEYS = {"live:talk": ("f9", 0x78), "live:cont": ("f10", 0x79)}


def log_path() -> str:
    return os.path.join(sp.workspace(), "logs", LOG_NAME)


def hotkeys_path() -> str:
    return os.path.join(sp.workspace(), HOTKEY_FILE)


def read_log() -> str:
    path = log_path()
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def clear_log() -> None:
    path = log_path()
    if os.path.exists(path):
        os.remove(path)


def press(vk: int) -> None:
    """Настоящее нажатие клавиши (keybd_event)."""
    user32 = ctypes.windll.user32
    user32.keybd_event(vk, 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


def start_exe() -> subprocess.Popen:
    return subprocess.Popen([EXE, "--enable-hotkeys"], cwd=os.path.dirname(EXE))


def wait_ready(proc: subprocess.Popen, timeout: float = 25.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if "РЕГИСТРАЦИЯ" in read_log():
            return True
        if proc.poll() is not None:
            return False
        time.sleep(0.4)
    return False


def stop(proc: subprocess.Popen) -> None:
    """Закрыть приложение.

    ВАЖНО: PyInstaller onefile — это ДВА процесса (родитель + ребёнок).
    terminate() убивает только родителя, а ребёнок остаётся жить и держит
    блокировку единственного экземпляра — следующий запуск не стартует.
    Поэтому гасим ВСЕ процессы приложения.
    """
    try:
        proc.terminate()
        proc.wait(timeout=8)
    except Exception:
        proc.kill()
    _kill_all_instances()


def _kill_all_instances() -> None:
    if os.name != "nt":
        return
    try:
        subprocess.run(["taskkill", "/F", "/IM", "RedZVoiceStudio.exe"],
                       capture_output=True, timeout=15)
    except Exception:
        pass
    time.sleep(1.5)


def scenario_defaults() -> bool:
    """Дефолтные комбинации должны зарегистрироваться все три."""
    print("=== 1. дефолтные комбинации регистрируются ===")
    # убираем сохранённые настройки, чтобы взять дефолты
    if os.path.exists(hotkeys_path()):
        os.remove(hotkeys_path())
    clear_log()
    proc = start_exe()
    ok = wait_ready(proc)
    if not ok:
        print("  приложение не стартовало")
        stop(proc)
        return False
    log = read_log()
    line = [ln for ln in log.splitlines() if "РЕГИСТРАЦИЯ" in ln]
    print(f"  {line[-1] if line else '(нет записи)'}")
    stop(proc)
    good = bool(line) and "НЕ Сработали" not in line[-1]
    print(f"  все три зарегистрированы: {'ок' if good else 'ошибка'}")
    return good


def scenario_single_key() -> bool:
    """Одиночная клавиша должна реально срабатывать."""
    print("\n=== 2. одиночная клавиша срабатывает (настоящее нажатие) ===")
    with open(hotkeys_path(), "w", encoding="utf-8") as fh:
        json.dump({action: name for action, (name, _vk) in TEST_KEYS.items()},
                  fh, ensure_ascii=False)
    clear_log()
    proc = start_exe()
    ok = wait_ready(proc)
    if not ok:
        print("  приложение не стартовало")
        stop(proc)
        return False

    fired = set()
    for action, (_name, vk) in TEST_KEYS.items():
        press(vk)
        time.sleep(1.0)
        if action in read_log():
            fired.add(action)
    stop(proc)

    for action, (name, _vk) in TEST_KEYS.items():
        state = "сработала" if action in fired else "НЕ Сработала"
        print(f"  {name:<10} ({action}) {state}")
    good = len(fired) == len(TEST_KEYS)
    print(f"  все одиночные клавиши сработали: {'ок' if good else 'ошибка'}")
    return good


def main() -> None:
    if not os.path.exists(EXE):
        print(f"нет EXE: {EXE}")
        raise SystemExit(1)

    _kill_all_instances()
    r1 = scenario_defaults()
    r2 = scenario_single_key()

    print("\n=== ИТОГ ===")
    print(f"  комбинации регистрируются: {'ок' if r1 else 'ошибка'}")
    print(f"  одиночные срабатывают:     {'ок' if r2 else 'ошибка'}")
    if not (r1 and r2):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
