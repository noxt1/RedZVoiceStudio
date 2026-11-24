"""Проверка оверлея: две строки (наша речь и речь игроков).

Запускает tools/overlay_win.py отдельным процессом, пишет в его файл две
строки и снимает экран — видно, что обе строки рисуются.

    python tools\\check_overlay_two.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import studio_paths as sp  # noqa: E402
from diag_overlay import grab, win_rect  # noqa: E402

user32 = __import__("ctypes").windll.user32


def find_overlay_window() -> int:
    """Найти окно оверлея по классу AuraloomOverlayWin (чистый Win32/GDI)."""
    import ctypes
    found = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p,
                                     ctypes.c_void_p)

    def cb(hwnd, lparam):  # noqa: ARG001
        cls = ctypes.create_unicode_buffer(128)
        user32.GetClassNameW(hwnd, cls, 128)
        if str(cls.value) == "AuraloomOverlayWin":
            l, t, r, b = win_rect(hwnd)
            if (r - l) > 100 and (b - t) > 20:
                found.append(hwnd)
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return found[0] if found else 0


def main() -> None:
    script = os.path.join(sp.workspace_tools(), "overlay_win.py")
    txt = os.path.join(sp.workspace(), "overlay_two.txt")
    with open(txt, "w", encoding="utf-8") as fh:
        fh.write("\n")

    engine = sp.engine_python()
    proc = subprocess.Popen([engine, script, txt], cwd=os.path.dirname(script),
                            creationflags=0x08000000)
    print(f"  запущен: {engine} {script}")
    time.sleep(4.0)

    # две строки: наша речь и речь другого игрока
    with open(txt, "w", encoding="utf-8") as fh:
        fh.write("Как круто, брат!\tQue chido, guay!\n"
                 "¡No te muevas!\tНе двигайся!")
    time.sleep(1.5)

    hwnd = find_overlay_window()
    if not hwnd:
        print("  окно оверлея не найдено")
        proc.terminate()
        return
    l, t, r, b = win_rect(hwnd)
    w, h = max(1, r - l), max(1, b - t)
    # берём область с запасом, чтобы увидеть, не вылезает ли текст
    img = grab(max(0, l - 10), max(0, t - 10), w + 240, h + 80)
    path = os.path.join(os.environ.get("TEMP", "."), "overlay_two.png")
    img.save(path)
    colors = img.getcolors(maxcolors=200000) or []
    bright = sum(c for c, col in colors if sum(col) > 600)
    yellow = sum(c for c, col in colors if col[0] > 150 and col[1] > 120
                 and col[2] < 140)
    print(f"  окно=({l},{t})-({r},{b})  светлых пикселей={bright}  "
          f"жёлтых (строка игроков)={yellow}")
    print(f"  снимок: {path}")
    print("  ТЕКСТ ВИДЕН" if bright > 200 else "  !! ТЕКСТ НЕ ВИДЕН")
    proc.terminate()
    try:
        os.remove(txt)
    except Exception:
        pass


if __name__ == "__main__":
    main()
