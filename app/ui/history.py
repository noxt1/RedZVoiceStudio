"""Боковая панель истории переводов и фраз.

Соответствует утверждённому дизайну:
- Выдвижная панель внизу навигации
- История последних переводов
- Банк фраз
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ui.theme import (
    ACCENT, BG, BORDER_SUBTLE, DIM, FG, GOOD, TEXT_MUTED, TEXT_PRIMARY,
    RADIUS_CARD, SPACE_M, SPACE_XS, SURFACE_1, FONT_BODY, FONT_SECONDARY,
)


class HistorySidebar(tk.Frame):
    """Выдвижная боковая панель с историей переводов и банком фраз."""

    def __init__(self, master, width=340, **kwargs):
        super().__init__(master, bg=SURFACE_1, width=width, **kwargs)
        self._width = width
        self._visible = False
        self._build()
        self.pack_propagate(False)

    def _build(self):
        # Заголовок
        header = tk.Frame(self, bg=BORDER_SUBTLE, height=1)
        header.pack(fill="x", padx=0, pady=0)

        title = tk.Label(
            self, text="История переводов",
            bg=SURFACE_1, fg=TEXT_PRIMARY, font=FONT_BODY, anchor="w")
        title.pack(fill="x", padx=SPACE_M, pady=(SPACE_M, SPACE_S))

        # Список переводов
        self.listbox = tk.Listbox(
            self, bg="#0b0d12", fg=TEXT_PRIMARY, selectbackground=ACCENT,
            selectforeground="#fff", font=FONT_SECONDARY,
            borderwidth=0, highlightthickness=0, activestyle="none")
        self.listbox.pack(fill="both", expand=True, padx=SPACE_M,
                          pady=(0, SPACE_M))

        # Банк фраз (кнопки быстрого доступа)
        bank = tk.Frame(self, bg=SURFACE_1)
        bank.pack(fill="x", padx=SPACE_M, pady=(0, SPACE_M))

        tk.Label(
            bank, text="Банк фраз", bg=SURFACE_1, fg=TEXT_MUTED,
            font=FONT_SECONDARY, anchor="w").pack(anchor="w")

        phrases = ["Привет!", "Как дела?", "Спасибо", "Пока"]
        for phrase in phrases:
            btn = tk.Button(
                bank, text=phrase, bg=BORDER_SUBTLE, fg=TEXT_PRIMARY,
                activeforeground=TEXT_PRIMARY, activebackground=SURFACE_HOVER,
                font=FONT_SECONDARY, relief="flat", cursor="hand2",
                padx=10, pady=6, highlightthickness=0, bd=0,
                anchor="w")
            btn.pack(fill="x", pady=1)
            btn.bind("<Enter>", lambda e, b=btn: b.configure(bg=SURFACE_HOVER))
            btn.bind("<Leave>", lambda e, b=btn: b.configure(bg=BORDER_SUBTLE))

    def add_translation(self, src: str, ru: str, direction: str = "out"):
        """Добавить запись в историю.

        direction: "out" (исходящий) или "in" (входящий).
        """
        marker = "→" if direction == "out" else "←"
        text = f"{marker} {src}" + (f"  →  {ru}" if ru else "")
        self.listbox.insert(0, text)
        # Ограничиваем историю 50 записями
        if self.listbox.size() > 50:
            self.listbox.delete(50, tk.END)

    def clear(self):
        self.listbox.delete(0, tk.END)

    def show(self):
        self._visible = True
        self.pack(side="right", fill="y", expand=False)

    def hide(self):
        self._visible = False
        self.pack_forget()

    def toggle(self):
        if self._visible:
            self.hide()
        else:
            self.show()
