"""Тест вкладки «6. Живой перевод» из ИСХОДНИКОВ.

Работает через настоящий mainloop (иначе tkinter ругается), ждёт
готовности движка и результата перевода.

    python tools\\test_live_src.py
"""

from __future__ import annotations

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import voice_studio  # noqa: E402


def main() -> None:
    studio = voice_studio.Studio()
    live = studio.live
    state = {"done": False}

    def step1():
        print("=== проверка вкладки ===")
        print("микрофон:", live.mic_combo.get())
        print("вывод:   ", live.out_combo.get())
        print("записей:", len(live._sample_files))
        # запускаем перевод записи (движок может ещё грузиться — запрос в очередь)
        live._test_with_sample()

    def step2():
        # ждём результата
        if live._last_es:
            print("\n=== РЕЗУЛЬТАТ ===")
            print("статус:", live.state_lbl.cget("text"))
            print("RU:    ", live._last_ru)
            print("ES:    ", live._last_es)
            state["done"] = True
            studio.root.quit()
            return
        if time.time() > deadline:
            print("\n=== РЕЗУЛЬТАТ ===")
            print("статус:", live.state_lbl.cget("text"))
            print("RU:    ", live._last_ru)
            print("ES:    ", live._last_es)
            state["done"] = True
            studio.root.quit()
            return
        studio.root.after(500, step2)

    deadline = time.time() + 240
    studio.root.after(600, step1)
    studio.root.after(1500, step2)
    studio.root.mainloop()

    try:
        if live.translator:
            live.translator.stop()
    except Exception:
        pass
    try:
        studio.root.destroy()
    except Exception:
        pass

    ok = bool(live._last_es)
    print("\nИТОГ:", "ок — перевод работает" if ok else "не сработало")
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
