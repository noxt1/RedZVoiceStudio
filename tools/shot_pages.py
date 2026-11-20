"""Скриншоты каждой страницы нового UI (диагностика отрисовки)."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import tkinter as _tk
from PIL import ImageGrab
from voice_studio import Studio
from ui.main_window import MainWindow

OUT = os.path.join(os.path.dirname(__file__), "..")


def shot(app, name):
    app.root.update_idletasks()
    app.root.update()
    app.root.after(600, app.root.quit)
    app.root.mainloop()
    app.root.update()
    x = app.root.winfo_rootx()
    y = app.root.winfo_rooty()
    w = app.root.winfo_width()
    h = app.root.winfo_height()
    img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
    path = os.path.join(OUT, f"page_{name}.png")
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

    shot(app, "home")

    app.nav.select("Голоса")
    shot(app, "voices")

    app.nav.select("Настройки")
    shot(app, "settings")

    app.nav.select("История и фразы")
    shot(app, "history")

    app.root.destroy()


if __name__ == "__main__":
    main()
