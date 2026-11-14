"""Нажать кнопку в окне установщика VB-CABLE.

Нужно, чтобы проверить установку моста автоматически: окно установщика
простое, кнопки ищутся по тексту.

    python tools\\click_installer.py ["Install Driver"] ["OK"]
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import sys
import time

user32 = ctypes.windll.user32

WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E
BM_CLICK = 0x00F5


def window_text(hwnd: int) -> str:
    n = user32.SendMessageW(hwnd, WM_GETTEXTLENGTH, 0, 0)
    buf = ctypes.create_unicode_buffer(n + 2)
    user32.SendMessageW(hwnd, WM_GETTEXT, n + 2, buf)
    return buf.value


def find_windows(needle: str) -> list[int]:
    found = []

    def cb(hwnd, _lparam):
        if needle.lower() in window_text(hwnd).lower():
            found.append(hwnd)
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return found


def find_child(parent: int, needle: str) -> int:
    found = []

    def cb(hwnd, _lparam):
        if needle.lower() in window_text(hwnd).lower():
            found.append(hwnd)
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    user32.EnumChildWindows(parent, WNDENUMPROC(cb), 0)
    return found[0] if found else 0


def main() -> None:
    buttons = sys.argv[1:] or ["Install Driver", "OK"]
    for label in buttons:
        wins = find_windows("VB-Audio")
        if not wins:
            print("окно установщика не найдено")
            return
        hwnd = wins[0]
        child = find_child(hwnd, label)
        if not child:
            print(f"кнопка «{label}» не найдена")
            continue
        print(f"нажимаю «{label}» (hwnd={child})")
        user32.SendMessageW(child, BM_CLICK, 0, 0)
        time.sleep(3.0)

    print("проверяю появившиеся устройства:")
    try:
        import sounddevice as sd
        for i, d in enumerate(sd.query_devices()):
            if "cable" in d["name"].lower():
                print(f"  [{i}] {d['name']}  вход={d['max_input_channels']} "
                      f"выход={d['max_output_channels']}")
    except Exception as exc:
        print("  ошибка:", exc)


if __name__ == "__main__":
    main()
