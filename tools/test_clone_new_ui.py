"""Проверка клонирования в новом UI (без запуска нейросети)."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import tkinter as _tk
import voice_studio as vs
from voice_studio import Studio
from ui.main_window import MainWindow


def main():
    studio = Studio(use_new_ui=True, root=None)
    app = MainWindow(studio)
    studio.root = app.root
    studio.tab_live = _tk.Frame(app.root, bg="#0B1118")
    studio._build_live()
    studio._populate_devices_new_ui()
    studio.sidebar = app.sidebar
    studio.lang = _tk.StringVar(value="ru")
    app.root.update()

    print("=== Заглушки нового UI ===")
    print("expr_var:", studio.expr_var)
    print("phrase_status:", type(studio.phrase_status).__name__)
    print("task_panel:", type(studio.task_panel).__name__)
    print("game_status:", type(studio.game_status).__name__)

    print()
    print("=== _bank_code ===")
    try:
        print("код банка:", studio._bank_code())
    except Exception as exc:
        print("ОШИБКА:", type(exc).__name__, exc)

    print()
    print("=== _voice_all (без реального клонирования) ===")
    # Подменяем тяжёлую функцию, чтобы проверить только обвязку
    import studio_core as core
    calls = {}

    def fake_clone_all(ref, attempts, on_line=None, texts=None,
                       expressiveness=0, lang="es"):
        calls["ref"] = ref
        calls["texts"] = len(texts or [])
        calls["expr"] = expressiveness
        calls["lang"] = lang
        if on_line:
            on_line("тест: всё ок")
        return 0

    orig = core.clone_all
    core.clone_all = fake_clone_all
    try:
        studio._voice_all()
        import time
        time.sleep(0.3)
        app.root.update()
        print("вызовов:", calls)
        print("статус:", studio.phrase_status.cget("text"))
        print("OK: _voice_all работает в новом UI")
    except Exception as exc:
        import traceback
        traceback.print_exc()
    finally:
        core.clone_all = orig

    app.root.destroy()


if __name__ == "__main__":
    main()