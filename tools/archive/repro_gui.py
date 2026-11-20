"""Репро с настоящим mainloop (как в EXE) + полный трейсбек.

Ключевое отличие от прошлого репро: окно реально крутит mainloop,
поэтому tkinter-переменные читаются из рабочего потока так же, как в
собранном приложении. Ошибка печатается целиком, а не обрезается до 80 символов.

    python tools\\repro_gui.py
"""

from __future__ import annotations

import os
import sys
import threading
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

import voice_studio  # noqa: E402


def main() -> None:
    studio = voice_studio.Studio()
    print(f"фраз в приложении: {len(studio.phrases)}")
    ids = [p["id"] for p in studio.phrases]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    print(f"дубликаты id: {dupes}")

    # ловим исключение из рабочего потока и печатаем целиком
    orig = voice_studio.Studio._run_job

    def patched(self, title, job, status=None, total=0, steps=None, panel=None):
        def wrapped(cb):
            try:
                return job(cb)
            except Exception:
                print("\n=== ПОЛНЫЙ ТРЕЙСБЕК ===", flush=True)
                traceback.print_exc()
                print("=== КОНЕЦ ТРЕЙСБЕКА ===\n", flush=True)
                raise
        return orig(self, title, wrapped, status=status, total=total,
                    steps=steps, panel=panel)

    voice_studio.Studio._run_job = patched

    def go():
        print("\nнажимаю «Озвучить всё моим голосом» ...", flush=True)
        try:
            studio._voice_all()
        except Exception:
            traceback.print_exc()
        # через 4 секунды покажем журнал и выйдем
        studio.root.after(4000, finish)

    def finish():
        print("\nстатус:", studio.phrase_status.cget("text"))
        try:
            print("журнал:")
            print(studio.task_panel.log_text.get("1.0", "end"))
        except Exception:
            pass
        studio.root.quit()

    studio.root.after(1200, go)
    studio.root.mainloop()


if __name__ == "__main__":
    main()
