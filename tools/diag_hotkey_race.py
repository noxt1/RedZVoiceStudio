"""Диагностика хоткеев: гонка при старте потока и Scroll_Lock.

Два вопроса:
  1. Теряется ли первая регистрация из-за гонки (поток-читатель ещё не
     создал очередь сообщений, а PostThreadMessageW уже ушёл)?
  2. Работает ли Scroll_Lock как глобальный хоткей (настоящая клавиатура
     шлёт его как EXTENDED-клавишу — scancode E0 46)?

    python tools\\diag_hotkey_race.py
"""

from __future__ import annotations

import ctypes
import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

import hotkeys as hk  # noqa: E402

user32 = ctypes.windll.user32


def test_race(trials: int = 40) -> bool:
    """Первая регистрация сразу после старта потока — теряется ли?"""
    print("=== 1. гонка: первая регистрация после start() ===")
    fails = 0
    slow = 0
    for i in range(trials):
        g = hk.GlobalHotkeys()
        t0 = time.time()
        ok = g.register("ctrl+alt+l", "live:cont", 0)
        dt = (time.time() - t0) * 1000
        if not ok:
            fails += 1
        if dt > 500:
            slow += 1
        g.unregister_all()
        if i < 3 or not ok or dt > 500:
            print(f"  попытка {i + 1:>3}: ok={ok}  {dt:6.0f} мс")
    print(f"  не зарегистрировано: {fails} из {trials}")
    print(f"  с задержкой >500 мс: {slow} из {trials}")
    print(f"  {'ЕСТЬ ГОНКА' if fails or slow else 'гонки нет'}")
    return fails == 0 and slow == 0


def test_scroll_lock() -> bool:
    """Scroll_Lock: обычное нажатие и расширенный scancode (как у клавиатуры)."""
    print("\n=== 2. Scroll_Lock как глобальный хоткей ===")
    fired = []
    g = hk.GlobalHotkeys()
    g.set_callback(lambda a: fired.append(a))
    ok = g.register("scroll_lock", "live:swap", 0)
    print(f"  регистрация: {ok}")
    if not ok:
        g.unregister_all()
        return False

    class KI(ctypes.Structure):
        _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                    ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                    ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

    class INPUT(ctypes.Structure):
        class _U(ctypes.Union):
            _fields_ = [("ki", KI), ("pad", ctypes.c_byte * 24)]

        _anonymous_ = ("u",)
        _fields_ = [("type", ctypes.c_ulong), ("u", _U)]

    INPUT_KEYBOARD = 1
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_SCANCODE = 0x0008

    def send_scan(scan: int, extended: bool) -> None:
        flags = KEYEVENTF_SCANCODE | (0x0001 if extended else 0)
        arr = (INPUT * 2)()
        arr[0].type = INPUT_KEYBOARD
        arr[0].ki = KI(0, scan, flags, 0, None)
        arr[1].type = INPUT_KEYBOARD
        arr[1].ki = KI(0, scan, flags | KEYEVENTF_KEYUP, 0, None)
        user32.SendInput(2, arr, ctypes.sizeof(INPUT))

    # 1) обычное нажатие (keybd_event по VK)
    fired.clear()
    user32.keybd_event(0x91, 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(0x91, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.6)
    print(f"  keybd_event(VK 0x91):        сработало = {bool(fired)}")

    # 2) как настоящая клавиатура: scancode 0x46 + EXTENDED
    fired.clear()
    send_scan(0x46, True)
    time.sleep(0.6)
    print(f"  SendInput(scan 0x46 EXT):    сработало = {bool(fired)}")

    # 3) scancode 0x46 без EXTENDED
    fired.clear()
    send_scan(0x46, False)
    time.sleep(0.6)
    print(f"  SendInput(scan 0x46 обычн.): сработало = {bool(fired)}")

    g.unregister_all()
    return bool(fired)


def test_combo_real_scancode() -> bool:
    """Комбинация Ctrl+Alt+буква с настоящими scancode."""
    print("\n=== 3. Ctrl+Alt+L с настоящими scancode ===")
    fired = []
    g = hk.GlobalHotkeys()
    g.set_callback(lambda a: fired.append(a))
    ok = g.register("ctrl+alt+l", "live:cont", 0)
    print(f"  регистрация: {ok}")
    if not ok:
        g.unregister_all()
        return False

    class KI(ctypes.Structure):
        _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                    ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                    ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

    class INPUT(ctypes.Structure):
        class _U(ctypes.Union):
            _fields_ = [("ki", KI), ("pad", ctypes.c_byte * 24)]

        _anonymous_ = ("u",)
        _fields_ = [("type", ctypes.c_ulong), ("u", _U)]

    INPUT_KEYBOARD = 1
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_SCANCODE = 0x0008

    def send(vk, scan, ext=False):
        flags = KEYEVENTF_SCANCODE | (0x0001 if ext else 0)
        arr = (INPUT * 2)()
        arr[0].type = INPUT_KEYBOARD
        arr[0].ki = KI(vk, scan, flags, 0, None)
        arr[1].type = INPUT_KEYBOARD
        arr[1].ki = KI(vk, scan, flags | KEYEVENTF_KEYUP, 0, None)
        user32.SendInput(2, arr, ctypes.sizeof(INPUT))

    fired.clear()
    send(0x11, 0x1D)          # Ctrl
    send(0x12, 0x38)          # Alt
    send(0x4C, 0x26)          # L
    time.sleep(0.1)
    send(0x4C, 0x26)
    send(0x12, 0x38)
    send(0x11, 0x1D)
    time.sleep(0.7)
    print(f"  сработало = {bool(fired)}  {fired}")
    g.unregister_all()
    return bool(fired)


def main() -> None:
    r1 = test_race()
    r2 = test_scroll_lock()
    r3 = test_combo_real_scancode()
    print("\n=== ИТОГ ===")
    print(f"  гонка при регистрации:  {'есть' if not r1 else 'нет'}")
    print(f"  Scroll_Lock работает:   {'да' if r2 else 'НЕТ'}")
    print(f"  Ctrl+Alt+L (scancode):  {'да' if r3 else 'НЕТ'}")


if __name__ == "__main__":
    main()
