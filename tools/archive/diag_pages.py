"""Диагностика всех страниц нового UI: что реально отрисовано."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import tkinter as _tk
from voice_studio import Studio
from ui.main_window import MainWindow


def count_widgets(w):
    """Рекурсивный подсчёт виджетов."""
    n = 1
    for c in w.winfo_children():
        n += count_widgets(c)
    return n


def main():
    studio = Studio(use_new_ui=True, root=None)
    app = MainWindow(studio)
    studio.root = app.root
    studio.tab_live = _tk.Frame(app.root, bg="#0B1118")
    studio._build_live()
    studio._populate_devices_new_ui()
    app.root.update()
    app.root.after(600, app.root.quit)
    app.root.mainloop()
    app.root.update()

    print("=== ГЛАВНАЯ ===")
    h = app.home
    print("виджетов:", count_widgets(h))
    print("кнопок:", len(h.btn_start_engine.winfo_children()) if hasattr(h, "btn_start_engine") else 0)
    print("history_list items:", h.history_list.size())

    print()
    print("=== ГОЛОСА ===")
    try:
        v = app.voices
        print("виджетов:", count_widgets(v))
        print("btn_rec:", hasattr(v, "btn_rec"))
        print("btn_clone:", hasattr(v, "btn_clone"))
        print("tree rows:", len(v.tree.get_children()))
        print("ref_status:", v.ref_status.cget("text")[:60])
    except Exception as exc:
        print("ОШИБКА:", exc)

    print()
    print("=== НАСТРОЙКИ ===")
    try:
        s = app.settings
        print("виджетов:", count_widgets(s))
        print("auto_cable_btn:", hasattr(s, "auto_cable_btn"))
        print("bridge_btn:", hasattr(s, "bridge_btn"))
        print("bridge_mic_combo values:", len(s.bridge_mic_combo["values"]))
        print("mic_combo values:", len(s.mic_combo["values"]))
        print("hk_enable_btn:", hasattr(s, "hk_enable_btn"))
    except Exception as exc:
        print("ОШИБКА:", exc)

    print()
    print("=== SIDEBAR (история) ===")
    sb = app.sidebar
    print("виджетов:", count_widgets(sb))
    print("listbox items:", sb.listbox.size())
    print("studio.sidebar:", studio.sidebar)

    print()
    print("=== LIVE TAB ===")
    live = studio.live
    print("monitor_vol:", live.monitor_vol.get())
    print("only_es:", getattr(live, "only_es", "НЕТ"))
    print("overlay_on:", getattr(live, "overlay_on", "НЕТ"))
    print("mic_combo:", live.mic_combo.get())
    print("lang_combo:", live.lang_combo.get())

    app.root.destroy()
    print()
    print("OK")


if __name__ == "__main__":
    main()
