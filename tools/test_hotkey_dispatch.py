"""Тест: доходит ли глобальный хоткей до интерфейса.

Подозрение: WM_HOTKEY приходит в поток-читатель, а обработчик дёргает
tkinter из НЕ главного потока -> RuntimeError, который глушится.

Проверяем: (1) приходит ли WM_HOTKEY; (2) что происходит при вызове
обработчика из чужого потока.

    python tools\\test_hotkey_dispatch.py
"""

from __future__ import annotations

import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

import hotkeys as hk  # noqa: E402


def main() -> None:
    print("=== 1. доходит ли WM_HOTKEY до колбэка ===")
    fired = []
    thread_of_cb = {}

    def cb(action):
        fired.append(action)
        thread_of_cb["id"] = threading.get_ident()

    g = hk.GlobalHotkeys()
    g.set_callback(cb)
    print("  регистрация scroll_lock:", g.register("scroll_lock", "live:swap", 0))
    g.start()
    time.sleep(0.8)
    print("  поток-читатель:", g._thread.ident, "| главный:", threading.get_ident())

    # имитируем доставку WM_HOTKEY в очередь потока-читателя
    import ctypes
    WM_HOTKEY = 0x0312
    hid = list(g._ids.keys())[0]
    ok = ctypes.windll.user32.PostThreadMessageW(g._thread.ident, WM_HOTKEY, hid, 0)
    deadline = time.time() + 3
    while time.time() < deadline and not fired:
        time.sleep(0.05)
    print(f"  сообщение отправлено: {bool(ok)}")
    print(f"  сработало: {fired}")
    print(f"  колбэк вызван в потоке {thread_of_cb.get('id')} "
          f"(читатель {g._thread.ident}, главный {threading.get_ident()})")
    in_reader = thread_of_cb.get("id") == g._thread.ident
    print(f"  колбэк пришёл из потока-читателя: {in_reader} "
          f"-> значит обработчик ДОЛЖЕН сам перекинуть в главный поток")

    print("\n=== 2. что будет, если обработчик дёрнет tkinter из потока-читателя ===")
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    lbl = tk.Label(root, text="x")
    err = {}

    def from_reader():
        try:
            lbl.config(text="y")
            err["ok"] = True
        except Exception as exc:
            err["ok"] = False
            err["exc"] = f"{type(exc).__name__}: {exc}"

    th = threading.Thread(target=from_reader)
    th.start()
    th.join()
    print(f"  tkinter из чужого потока: {'прошло' if err.get('ok') else 'УПАЛО -> ' + err.get('exc', '')}")

    try:
        root.after(0, lambda: None)
        root.update()
    except Exception:
        pass
    root.destroy()
    g.unregister_all()

    print("\n=== ИТОГ ===")
    if fired and not err.get("ok", True):
        print("  ПРИЧИНА найдена: хоткей доходит, но обработчик падает")
        print("  (tkinter из потока-читателя) -> исключение глушится в цикле.")
    elif fired:
        print("  хоткей доходит и обработчик в порядке")
    else:
        print("  WM_HOTKEY НЕ доходит — проблема в доставке сообщения")


if __name__ == "__main__":
    main()
