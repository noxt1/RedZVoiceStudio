"""Скриншоты трёх под-вкладок «Голоса» + проверка сценария записи."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import tkinter as _tk  # noqa: E402
from PIL import ImageGrab  # noqa: E402

from voice_studio import Studio  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "shots")


def shot(app, name):
    app.root.update_idletasks()
    app.root.update()
    app.root.after(700, app.root.quit)
    app.root.mainloop()
    app.root.update()
    x = app.root.winfo_rootx()
    y = app.root.winfo_rooty()
    w = app.root.winfo_width()
    h = app.root.winfo_height()
    img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"voices_{name}.png")
    img.save(path)
    print(f"{name}: {w}x{h} -> {path}")


def main():
    studio = Studio(use_new_ui=True, root=None)
    app = MainWindow(studio)
    studio.root = app.root
    studio.tab_live = _tk.Frame(app.root, bg="#0B1118")
    studio._build_live()
    studio._populate_devices_new_ui()
    studio.sidebar = app.sidebar
    app.root.update()
    app.root.after(600, app.root.quit)
    app.root.mainloop()

    app.nav.select("Голоса")
    app.root.update()
    page = app.voices

    print("готовые подсказки:",
          __import__("prompt_library").available())
    print("элементов в манифесте:",
          len(__import__("prompt_library").manifest()))

    # 1. Плитка записи
    page._select_tab("quick")
    shot(app, "1_quick")

    # 2. Плитка в состоянии «фраза показана»
    page._quick_active = True
    page._quick_index = 2
    items = __import__("prompt_library").manifest()
    if len(items) > 2:
        it = items[2]
        page.prompt_text.config(text=it["ru"].replace("{name}", "Cyril"))
        page.prompt_emo.config(text=f"Интонация: {it['emotion_label']}")
        page.quick_step.config(text="Фраза 3 из 18")
        page._progress_value = 2 / 18
        page._draw_progress()
        page.quick_status.config(text="✔  ок — запись нормальная (2.8 c). "
                                      "Сравни с образцом или жми «Дальше».",
                                 fg="#55D6A2")
        page.btn_next.config(state="normal")
        page.btn_redo.config(state="normal")
        page.btn_compare.config(state="normal")
    app.root.update()
    shot(app, "2_quick_phrase")

    # 3. Подсказки
    page._select_tab("prompts")
    shot(app, "3_prompts")

    # 4. Образцы
    page._select_tab("samples")
    shot(app, "4_samples")

    app.root.destroy()


if __name__ == "__main__":
    main()
