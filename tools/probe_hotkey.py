"""Проверка: доходит ли WM_HOTKEY в этом окружении при синтетическом вводе.

Нужно, чтобы отличить «баг в коде» от «Windows не доставляет сообщение
на синтетический ввод keybd_event из консольного процесса».

    python tools\\probe_hotkey.py
"""

from __future__ import annotations

import ctypes
import os
import sys
import time
from ctypes import wintypes

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))

import hotkeys as hk  # noqa: E402

u = ctypes.windll.user32


WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_long, wintypes.HWND, ctypes.c_uint,
                              wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASS(ctypes.Structure):
    _fields_ = [("style", ctypes.c_uint32), ("lpfnWndProc", ctypes.c_void_p),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]


def probe_with_window() -> None:
    """Своё окно со своим WndProc — ловим WM_HOTKEY напрямую."""
    fired = []

    def proc(hwnd, msg, wparam, lparam):
        if msg == 0x0312:
            fired.append(wparam)
            return 0
        return u.DefWindowProcW(hwnd, msg, wparam, lparam)

    WNDCLASS = globals()["WNDCLASS"]()
    WNDCLASS.lpfnWndProc = ctypes.cast(
        ctypes.WINFUNCTYPE(ctypes.c_long, wintypes.HWND, ctypes.c_uint,
                           wintypes.WPARAM, wintypes.LPARAM)(proc),
        ctypes.c_void_p)
    WNDCLASS.hInstance = ctypes.windll.kernel32.GetModuleHandleW(None)
    WNDCLASS.lpszClassName = "TestHotkeyWnd"
    u.RegisterClassW(ctypes.byref(WNDCLASS))
    hwnd = u.CreateWindowExW(0, "TestHotkeyWnd", "test", 0, 0, 0, 0, 0,
                              0, 0, 0, None)
    print(f"окно создано: {hwnd}")
    hid = 0xB999
    mods = hk.MOD_CONTROL | hk.MOD_ALT | hk.MOD_SHIFT
    ok = u.RegisterHotKey(hwnd, hid, mods | hk.MOD_NOREPEAT, 0x78)  # F9
    print(f"RegisterHotKey: {ok}")
    time.sleep(0.3)

    for vk in (0x11, 0x12, 0x10, 0x78):
        u.keybd_event(vk, 0, 0, 0)
    time.sleep(0.05)
    for vk in (0x78, 0x10, 0x12, 0x11):
        u.keybd_event(vk, 0, 2, 0)
    time.sleep(1.0)
    print(f"пришло WM_HOTKEY: {fired}")
    u.UnregisterHotKey(hwnd, hid)


def probe_global() -> None:
    """Через наш GlobalHotkeys + синтетический ввод."""
    fired = []
    g = hk.GlobalHotkeys()
    g.set_callback(lambda a: fired.append(a))
    g.register("f9", "live:cont", hk.MOD_CONTROL | hk.MOD_ALT | hk.MOD_SHIFT)
    g.start()
    time.sleep(0.8)
    print(f"зарегистрировано: {g.registered()} | поток жив: {g._thread.is_alive()}")

    for vk in (0x11, 0x12, 0x10, 0x78):
        u.keybd_event(vk, 0, 0, 0)
    time.sleep(0.05)
    for vk in (0x78, 0x10, 0x12, 0x11):
        u.keybd_event(vk, 0, 2, 0)
    time.sleep(1.0)
    print(f"сработало: {fired}")
    g.unregister_all()


if __name__ == "__main__":
    print("=== своё окно ===")
    probe_with_window()
    print("\n=== наш GlobalHotkeys ===")
    probe_global()
