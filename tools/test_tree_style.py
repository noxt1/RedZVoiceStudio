"""Диагностика фона ttk.Treeview (белая полоса под строками)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import tkinter as tk
from tkinter import ttk
from PIL import ImageGrab

from ui.theme import ACCENT, SURFACE_1, SURFACE_2, SURFACE_3, TEXT_PRIMARY, TEXT_SECONDARY

root = tk.Tk()
root.geometry("700x300")
root.configure(bg="#0B1118")

style = ttk.Style(root)
print("theme:", style.theme_use())
style.layout("Treeview.Dark", style.layout("Treeview"))
style.layout("Treeview.Dark.Heading", style.layout("Treeview.Heading"))
style.configure("Treeview.Dark", background=SURFACE_1, fieldbackground=SURFACE_1,
                foreground=TEXT_PRIMARY, borderwidth=0, rowheight=24)
style.configure("Treeview.Dark.Heading", background=SURFACE_2,
                foreground=TEXT_SECONDARY, borderwidth=0, relief="flat")
style.map("Treeview.Dark", background=[("selected", ACCENT)],
          foreground=[("selected", "#0B1118")])

f = tk.Frame(root, bg="#0B1118")
f.pack(fill="both", expand=True, padx=10, pady=10)

tv = ttk.Treeview(f, columns=("a", "b"), show="headings", height=3,
                   style="Treeview.Dark")
tv.heading("a", text="A")
tv.heading("b", text="B")
for i in range(3):
    tv.insert("", "end", values=(f"строка {i}", "значение"))
tv.pack(side="left", fill="both", expand=True)
sb = ttk.Scrollbar(f, orient="vertical", command=tv.yview)
tv.configure(yscrollcommand=sb.set)
sb.pack(side="right", fill="y")

root.update_idletasks()
root.update()
root.attributes("-topmost", True)
root.lift()
root.focus_force()
for _ in range(20):
    root.update()
    root.after(20)
root.update_idletasks()
root.update()
x = root.winfo_rootx()
y = root.winfo_rooty()
w = root.winfo_width()
h = root.winfo_height()
img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
out = os.path.join(os.path.dirname(__file__), "..", "shots", "tree_test.png")
os.makedirs(os.path.dirname(out), exist_ok=True)
img.save(out)
print("saved:", out)
print("tree height:", tv.winfo_height(), "rows:", 3 * 24)
print("field options:", style.lookup("Treeview.Dark", "fieldbackground"),
      "| background:", style.lookup("Treeview.Dark", "background"))
root.destroy()
