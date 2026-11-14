"""Минимальный тест цикла чтения WM_HOTKEY из очереди потока.

Проверяет саму идею: PostThreadMessage -> PeekMessage в потоке -> callback.

    python tools\\probe_peek.py
"""

from __future__ import annotations

import ctypes
import threading
import time
from ctypes import wintypes

wt = wintypes

u = ctypes.windll.user32
WM_HOTKEY = 0x0312
PM_NOREMOVE = 0x0000
PM_REMOVE = 0x0001


def main() -> None:
    got = []

    def loop_peek():
        while True:
            msg = wt.MSG()
            r = u.PeekMessageW(ctypes.byref(msg), None, 0, 0, 50)
            if r:
                print("  peek: сообщение", msg.message, "wParam", msg.wParam)
                if msg.message == WM_HOTKEY:
                    got.append(("peek", msg.wParam))
                    break

    def loop_get():
        while True:
            msg = wt.MSG()
            r = u.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if r in (0, -1):
                break
            print("  get: сообщение", msg.message, "wParam", msg.wParam)
            if msg.message == WM_HOTKEY:
                got.append(("get", msg.wParam))
                break

    for name, loop in (("PeekMessage", loop_peek), ("GetMessage", loop_get)):
        got.clear()
        th = threading.Thread(target=loop, daemon=True)
        th.start()
        time.sleep(0.6)
        ok = u.PostThreadMessageW(th.ident, WM_HOTKEY, 0xB999, 0)
        deadline = time.time() + 2.5
        while time.time() < deadline and not got:
            time.sleep(0.1)
        print(f"{name}: PostThreadMessage={bool(ok)} получено={got}")

    print("ВЫВОД: цикл читает WM_HOTKEY из очереди потока" if got else
          "ВЫВОД: сообщения в очередь потока не доходят")


if __name__ == "__main__":
    main()
