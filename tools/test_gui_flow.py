"""Интеграционный тест: кнопка «Озвучить моим голосом» -> файл -> панель.

Проверяет весь путь целиком:
  1. нажатие кнопки не застревает (busy сбрасывается);
  2. файл реально появляется в out/mp3;
  3. панель задачи показывает этапы и финальный вердикт.

    python tools\\test_gui_flow.py
"""

from __future__ import annotations

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

import voice_studio  # noqa: E402


def main() -> None:
    studio = voice_studio.Studio()
    studio.root.withdraw()  # не показывать окно в тесте

    phrase = studio.phrases[-1]
    pid = phrase["id"]
    import studio_paths as sp
    target = os.path.join(sp.output_paths()["out_mp3"], f"mx_{pid}.mp3")
    if os.path.exists(target):
        os.remove(target)

    print(f"озвучиваю фразу {pid}: {phrase['text']}")
    # выбираем строку в таблице (иначе кнопка «Озвучить моим голосом» без выбора)
    studio.phrase_tree.selection_set(len(studio.phrases) - 1)
    studio._voice_custom()

    # ждём завершения (поток + after)
    deadline = time.time() + 240
    while time.time() < deadline:
        studio.root.update()
        if not studio.busy and os.path.exists(target):
            break
        time.sleep(0.4)

    ok_file = os.path.exists(target)
    panel = studio.task_panel
    steps = [(s["status"], s["title"]) for s in panel._steps]
    print("\nфайл создан:", ok_file, "->", os.path.basename(target))
    print("этапы:")
    for status, title in steps:
        mark = {"todo": "·", "doing": "▸", "done": "✓", "fail": "✗"}[status]
        print(f"   {mark} {title}")
    print("busy сброшен:", not studio.busy)
    print("статус:", studio.phrase_status.cget("text"))

    studio.root.destroy()

    if not ok_file:
        raise SystemExit("файл не создан")
    if studio.busy:
        raise SystemExit("busy не сброшен")
    if all(s == "todo" for s, _ in steps):
        raise SystemExit("этапы не обновлены")
    print("\nИТОГ: ок — кнопка отработала, файл создан, этапы видны.")


if __name__ == "__main__":
    main()
