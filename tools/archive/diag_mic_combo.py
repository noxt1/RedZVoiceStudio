"""Проверка: заполнен ли mic_combo у LiveTab в новом UI."""

from __future__ import annotations

import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_APP = os.path.join(_ROOT, "app")
if _APP not in sys.path:
    sys.path.insert(0, _APP)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import tkinter as tk
import studio_paths as sp
sp.seed_workspace()
import voice_studio as vs

studio = vs.Studio(use_new_ui=True, root=None)
from ui.main_window import MainWindow
app = MainWindow(studio)
studio.root = app.root
studio.sidebar = app.sidebar
studio.lang = tk.StringVar(value="ru")
studio.tab_live = tk.Frame(app.root, bg=vs.BG)
studio._build_live()

# даём after(300) сработать
for _ in range(60):
    app.root.update()
    time.sleep(0.02)

live = studio.live
print("live:", type(live).__name__)
print()

print("=== mic_combo ===")
print("exists:", hasattr(live, "mic_combo"))
if hasattr(live, "mic_combo"):
    print("values:", live.mic_combo.cget("values"))
    print("current:", repr(live.mic_combo.get()))

print()
print("=== _sel_mic() ===")
try:
    print("_sel_mic ->", live._sel_mic())
except Exception as exc:
    print("ОШИБКА:", type(exc).__name__, exc)

print()
print("=== _inputs ===")
print("live._inputs:", getattr(live, "_inputs", "нет"))
print("studio.in_device:", getattr(studio, "in_device", "нет"))

print()
print("=== _ensure_engine ===")
print("translator:", live.translator)

root = app.root
root.destroy()