"""Проверка авто-маршрута под виртуальный кабель (мост реально стартует)."""
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

    app.nav.select("Настройки")
    app.root.update()
    app.root.after(300, app.root.quit)
    app.root.mainloop()
    app.root.update()

    print("=== Авто-маршрут под кабель ===")
    app.settings._auto_setup_cable()
    app.root.update()

    bridge = getattr(studio, "bridge", None)
    print("мост создан:", bridge is not None)
    if bridge is not None:
        print("мост running:", bridge.running)
        print("mic_device:", bridge.mic_device)
        print("render_device:", bridge.render_device)
        print("monitor_device:", bridge.monitor_device)
        st = bridge.status()
        print(f"mic_peak={st['mic_peak']:.4f} out_peak={st['out_peak']:.4f} sr={st['sr']}")
    print("статус в UI:", app.settings.bridge_status.cget("text"))
    print("studio.out_device:", studio.out_device)
    print("studio.in_device:", studio.in_device)
    print("live selected out:", studio.live.get_selected_out())
    print("live selected mic:", studio.live.get_selected_mic())

    # Останавливаем мост
    if bridge is not None:
        bridge.stop()
        studio.bridge = None
    app.root.destroy()
    print()
    print("OK")


if __name__ == "__main__":
    main()
