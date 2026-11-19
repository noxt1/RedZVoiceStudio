"""Проверка интеграции нового UI с LiveTab (Этап C.7.2)."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import tkinter as _tk
from voice_studio import Studio
from ui.main_window import MainWindow


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

    # Открываем настройки
    app.nav.select("Настройки")
    app.root.update()
    app.root.after(500, app.root.quit)
    app.root.mainloop()
    app.root.update()

    s = app.settings
    print("=== Настройки ===")
    print("bridge_mic_combo:", s.bridge_mic_combo.get())
    print("bridge_out_combo:", s.bridge_out_combo.get())
    print("auto_cable_btn:", s.auto_cable_btn.cget("text"))
    print("bridge_btn:", s.bridge_btn.cget("text"))
    print("duck_var:", s.duck_var.get())
    print("mic_combo:", s.mic_combo.get())
    print("out_combo:", s.out_combo.get())
    print("capture_combo:", s.capture_combo.get())

    print()
    print("=== Кабели в системе ===")
    try:
        import cable
        print("cable_devices():", cable.cable_devices())
    except Exception as exc:
        print("cable error:", exc)

    print()
    print("=== Авто-маршрут (анализ) ===")
    try:
        import hotkeys as hk
        inputs, outputs = hk.list_devices()
        print("inputs:", len(inputs), "outputs:", len(outputs))
        mix_idx, mix_name = hk.find_stereo_mix(inputs)
        print("Stereo Mix:", mix_idx, mix_name)
        render_idx, render_name = hk.find_render_for_capture(inputs, outputs)
        print("render for capture:", render_idx, render_name)
        virt = [(i, n) for i, n in outputs if hk.is_virtual_cable(n)]
        print("virtual cables:", virt)
    except Exception as exc:
        print("error:", exc)

    app.root.destroy()
    print()
    print("OK")


if __name__ == "__main__":
    main()
