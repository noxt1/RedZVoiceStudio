"""Боковая панель истории переводов и фраз.

Выдвижная панель справа, открывается через навигацию или F12.
Загружает реальную историю из логов движка и фразы из lines.json.
"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk

import studio_core as core
import studio_paths as sp

from ui.theme import (
    ACCENT, BG, BORDER_SUBTLE, DIM, FG, FONT_BODY, FONT_SECONDARY,
    HOVER, RADIUS_CARD, SPACE_M, SPACE_S, SPACE_XS, SURFACE_1, TEXT_MUTED,
    TEXT_PRIMARY,
)


class Sidebar(tk.Frame):
    """Выдвижная боковая панель с историей переводов и банком фраз."""

    def __init__(self, master, width=340, **kwargs):
        super().__init__(master, bg=SURFACE_1, width=width, **kwargs)
        self._width = width
        self._visible = False
        self._build()
        self.pack_propagate(False)
        # Загружаем реальную историю из логов
        self._load_history()

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

        # Пустое состояние
        self.empty_lbl = tk.Label(
            self, text="История пуста — переводы появятся здесь",
            bg="#0b0d12", fg=TEXT_MUTED, font=FONT_SECONDARY, anchor="center")
        self.empty_lbl.pack(expand=True)
        self._update_empty_state()

        # Банк фраз (реальные фразы из lines.json)
        bank = tk.Frame(self, bg=SURFACE_1)
        bank.pack(fill="x", padx=SPACE_M, pady=(0, SPACE_M))

        tk.Label(
            bank, text="Банк фраз", bg=SURFACE_1, fg=TEXT_MUTED,
            font=FONT_SECONDARY, anchor="w").pack(anchor="w")

        # Загружаем фразы из lines.json (первые 4 для компактности)
        try:
            lines = core.load_lines()
            phrases = [line.get("es", "") for line in lines[:4] if line.get("es")]
        except Exception:
            phrases = []
        if not phrases:
            phrases = ["Привет!", "Как дела?", "Спасибо", "Пока"]

        for phrase in phrases:
            btn = tk.Button(
                bank, text=phrase, bg=BORDER_SUBTLE, fg=TEXT_PRIMARY,
                activeforeground=TEXT_PRIMARY, activebackground=HOVER,
                font=FONT_SECONDARY, relief="flat", cursor="hand2",
                padx=10, pady=6, highlightthickness=0, bd=0,
                anchor="w")
            btn.pack(fill="x", pady=1)
            btn.bind("<Enter>", lambda e, b=btn: b.configure(bg=HOVER))
            btn.bind("<Leave>", lambda e, b=btn: b.configure(bg=BORDER_SUBTLE))

    def _load_history(self):
        """Загрузить историю переводов из лога движка."""
        log_path = os.path.join(sp.workspace(), "logs", "live_engine.log")
        if not os.path.exists(log_path):
            return
        try:
            with open(log_path, encoding="utf-8") as fh:
                lines = fh.readlines()
        except Exception:
            return
        # Ищем строки с переводами: "[gui] ..." или строки с RU/ES
        count = 0
        for line in reversed(lines[-200:]):  # последние 200 строк
            line = line.strip()
            if not line:
                continue
            # Пытаемся извлечь пару RU → ES из лога
            # Формат может быть разным — ищем паттерны перевода
            if "RU" in line or "ES" in line or "→" in line:
                # Пропадные служебные строки
                if any(k in line.lower() for k in ("error", "traceback", "exception", "запуск", "ошибка")):
                    continue
                text = line[:80]
                self.listbox.insert(0, f"• {text}")
                count += 1
                if count >= 20:
                    break
        self._update_empty_state()

    def _update_empty_state(self):
        """Показать/скрыть надпись о пустой истории."""
        if self.listbox.size() == 0:
            self.empty_lbl.pack(expand=True)
        else:
            self.empty_lbl.pack_forget()

    def add_translation(self, src: str, ru: str, direction: str = "out"):
        """Добавить запись в историю.

        direction: "out" (исходящий) или "in" (входящий).
        """
        marker = "→" if direction == "out" else "←"
        text = f"{marker} {src}" + (f"  →  {ru}" if ru else "")
        self.listbox.insert(0, text)
        self._update_empty_state()
        # Ограничиваем историю 50 записями
        if self.listbox.size() > 50:
            self.listbox.delete(50, tk.END)

    def clear(self):
        self.listbox.delete(0, tk.END)
        self._update_empty_state()

    def show(self):
        self._visible = True
        # Основное окно использует grid — используем grid и здесь
        self.grid(row=0, column=2, sticky="ns")

    def hide(self):
        self._visible = False
        self.grid_remove()

    def toggle(self):
        if self._visible:
            self.hide()
        else:
            self.show()