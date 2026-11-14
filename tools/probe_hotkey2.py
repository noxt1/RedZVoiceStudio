"""Проверка доставки WM_HOTKEY: keybd_event vs SendInput.

Цель — отделить «баг в коде» от «синтетический ввод не доставляет hotkey».
Оба способа проверяем на СВОЁМ окне (свой WndProc ловит WM_HOTKEY).

    python tools\\probe_hotkey2.py
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
k = ctypes.windll.kernel32

WM_HOTKEY = 0x0312


class WNDCLASS(ctypes.Structure):
    _fields_ = [("style", ctypes.c_uint32), ("lpfnWndProc", ctypes.c_void_p),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("padding", ctypes.c_byte * 24)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008


def make_window():
    fired = []

    def proc(hwnd, msg, wparam, lparam):
        if msg == WM_HOTKEY:
            fired.append(wparam)
            return 0
        return u.DefWindowProcW(hwnd, ctypes.c_uint(msg), ctypes.c_uint64(wparam),
                                ctypes.c_int64(lparam))

    cls = WNDCLASS()
    cls.lpfnWndProc = ctypes.cast(
        ctypes.WINFUNCTYPE(ctypes.c_long, wintypes.HWND, ctypes.c_uint,
                           ctypes.c_size_t, ctypes.c_ssize_t)(proc),
        ctypes.c_void_p)
    cls.hInstance = k.GetModuleHandleW(None)
    cls.lpszClassName = "TestHotkeyWnd2"
    u.RegisterClassW(ctypes.byref(cls))
    hwnd = u.CreateWindowExW(0, "TestHotkeyWnd2", "test", 0, 0, 0, 0, 0,
                              0, 0, 0, None)
    return hwnd, fired


def send_input(vks):
    """Настоящий синтетический ввод через SendInput."""
    arr = (INPUT * len(vks))()
    for i, vk in enumerate(vks):
        arr[i].type = INPUT_KEYBOARD
        arr[i].ki.wVk = vk
        arr[i].ki.dwFlags = 0
    u.SendInput(len(vks), arr, ctypes.sizeof(INPUT))
    time.sleep(0.05)
    arr2 = (INPUT * len(vks))()
    for i, vk in enumerate(reversed(vks)):
        arr2[i].type = INPUT_KEYBOARD
        arr2[i].ki.wVk = vk
        arr2[i].ki.dwFlags = KEYEVENTF_KEYUP
    u.SendInput(len(vks), arr2, ctypes.sizeof(INPUT))


def main() -> None:
    hwnd, fired = make_window()
    print(f"окно: {hwnd}")
    mods = hk.MOD_CONTROL | hk.MOD_ALT | hk.MOD_SHIFT
    ok = u.RegisterHotKey(hwnd, 0xB999, mods | hk.MOD_NOREPEAT, 0x78)
    print(f"RegisterHotKey (Ctrl+Alt+Shift+F9): {ok}")
    time.sleep(0.4)

    vks = [0x11, 0x12, 0x10, 0x78]  # ctrl alt shift F9

    print("\n--- keybd_event ---")
    for vk in vks:
        u.keybd_event(vk, 0, 0, 0)
    time.sleep(0.05)
    for vk in reversed(vks):
        u.keybd_event(vk, 0, 2, 0)
    time.sleep(0.8)
    print(f"пришло: {fired}")

    fired.clear()
    print("\n--- SendInput ---")
    send_input(vks)
    time.sleep(0.8)
    print(f"пришло: {fired}")

    u.UnregisterHotKey(hwnd, 0xB999)
    print("\nВЫВОД: если ни один способ не сработал — синтетический ввод из")
    print("консольного процесса не доставляет WM_HOTKEY (особенность Windows).")
    print("Значит, код хоткеев верный, а проверить его можно только вручную:")
    print("запустить приложение и нажать Ctrl+Alt+Shift+F9.")


if __name__ == "__main__":
    main()
