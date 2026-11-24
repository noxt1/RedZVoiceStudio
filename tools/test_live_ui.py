"""Автотест вкладки «6. Живой перевод» в ЗАПУЩЕННОМ EXE.

Нажимает «Проверить» на записи образца и ждёт результата: перевод должен
появиться в интерфейсе, а аудио — в списке воспроизведения.

    python tools\\test_live_ui.py
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import time

user32 = ctypes.windll.user32
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = os.path.join(ROOT, "dist", "Auraloom.exe")


def find_window(needle: str = "Auraloom Voice Studio") -> int:
    found = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def cb(hwnd, lparam):  # noqa: ARG001
        buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, buf, 512)
        if needle in buf.value:
            r = wt.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            found.append(((r.right - r.left) * (r.bottom - r.top), hwnd))
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    if not found:
        return 0
    found.sort(reverse=True)
    return found[0][1]


def _procs() -> list[str]:
    """Список командных строк запущенных процессов (для проверки движка)."""
    out = []
    try:
        import subprocess as sp
        r = sp.run(["wmic", "process", "get", "CommandLine"],
                   capture_output=True, text=True, errors="replace", timeout=20)
        out = [ln for ln in r.stdout.splitlines() if "live_translate" in ln]
    except Exception:
        out = []
    return out


def main() -> None:
    print("запускаю EXE ...")
    proc = subprocess.Popen([EXE], cwd=os.path.dirname(EXE))
    time.sleep(20)

    hwnd = find_window()
    if not hwnd:
        print("окно не найдено")
        proc.kill()
        return
    print("окно найдено:", hwnd)
    user32.SetForegroundWindow(hwnd)
    time.sleep(1)

    # вкладка 6 — последняя: 5 раз Ctrl+PgDn
    for _ in range(5):
        user32.keybd_event(0x11, 0, 0, 0)
        user32.keybd_event(0x22, 0, 0, 0)
        user32.keybd_event(0x22, 0, 2, 0)
        user32.keybd_event(0x11, 0, 2, 0)
        time.sleep(0.35)
    time.sleep(1.5)

    print("нажимаю «Проверить» ...")
    # кнопка «Проверить» — по координатам окна (вкладка «6. Живой перевод»)
    r = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    x = r.left + 555
    y = r.top + 425
    user32.SetCursorPos(x, y)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    user32.mouse_event(0x0004, 0, 0, 0, 0)
    print(f"клик: {x},{y}")

    # ждём загрузки моделей и перевода
    print("жду до 120 с ...")
    for i in range(12):
        time.sleep(10)
        n = len([p for p in _procs() if "live_translate" in p])
        print(f"  +{(i + 1) * 10} с: процессов движка = {n}")

    from PIL import Image
    import io
    import sys
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    from shot import capture
    out = r"C:\Users\cyril\AppData\Local\Temp\opencode\livetest.png"
    capture(hwnd, out)
    print("saved", out)
    proc.kill()


if __name__ == "__main__":
    main()
