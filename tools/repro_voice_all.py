"""Репро ошибки PermissionError в «Озвучить всё моим голосом».

Запускает GUI из исходников, нажимает ту же кнопку и печатает ПОЛНЫЙ
трейсбек исключения (в GUI он обрезается до 80 символов).

    python tools\\repro_voice_all.py
"""

from __future__ import annotations

import os
import sys
import time
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

import voice_studio  # noqa: E402
import studio_core as core  # noqa: E402


def main() -> None:
    studio = voice_studio.Studio()
    studio.root.withdraw()

    print(f"фраз в приложении: {len(studio.phrases)}")
    ids = [p["id"] for p in studio.phrases]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    print(f"дубликаты id: {dupes}")

    # перехватываем исключение из рабочего потока GUI
    orig = voice_studio.Studio._run_job

    def patched(self, title, job, status=None, total=0, steps=None, panel=None):
        def wrapped(cb):
            try:
                return job(cb)
            except Exception:
                print("\n=== ПОЛНЫЙ ТРЕЙСБЕК ===")
                traceback.print_exc()
                print("=== КОНЕЦ ТРЕЙСБЕКА ===\n")
                raise
        return orig(self, title, wrapped, status=status, total=total,
                    steps=steps, panel=panel)

    voice_studio.Studio._run_job = patched

    print("\nнажимаю «Озвучить всё моим голосом» ...")
    studio._voice_all()

    deadline = time.time() + 90
    while time.time() < deadline:
        studio.root.update()
        if not studio.busy:
            break
        time.sleep(0.3)

    print("статус:", studio.phrase_status.cget("text"))
    studio.root.destroy()


if __name__ == "__main__":
    main()
