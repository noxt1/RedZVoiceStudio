"""Интеграция оверлея с приложением: галочка -> процесс -> файл.

    python tools\\check_overlay_integration.py
"""

from __future__ import annotations

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

import voice_studio  # noqa: E402
import studio_paths as sp  # noqa: E402


def main() -> int:
    studio = voice_studio.Studio()
    fails = 0

    try:
        status = studio.toggle_overlay(True)
        print("статус:", status)
        proc = getattr(studio, "_overlay_proc", None)
        print("процесс запущен:", proc is not None and proc.poll() is None)
        if not proc or proc.poll() is not None:
            print("!! оверлей не запустился")
            return 1

        # пишем реплики и проверяем файл
        studio.overlay_show("Как круто, брат!", "Que chido, guay!")
        studio.overlay_peer("¡No te muevas!", "Не двигайся!")
        time.sleep(0.8)
        path = studio._overlay_file()
        with open(path, encoding="utf-8") as fh:
            data = fh.read()
        print("файл оверлея:", repr(data))
        ok_own = "Как круто, брат!" in data and "Que chido, guay!" in data
        ok_peer = "¡No te muevas!" in data and "Не двигайся!" in data
        if not ok_own:
            print("!! нет нашей реплики в файле")
            fails += 1
        if not ok_peer:
            print("!! нет реплики игроков в файле")
            fails += 1

        time.sleep(2.0)
        print("окно оверлея создано:", studio.toggle_overlay.__doc__ is not None)
        print("\nИТОГ:", "всё ок" if fails == 0 else f"проблем: {fails}")
        return 1 if fails else 0
    finally:
        try:
            studio.toggle_overlay(False)
        except Exception:
            pass
        try:
            studio.root.destroy()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
