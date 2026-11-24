"""Навигация по трём разделам: Главная / Голоса / Настройки.

Соответствует утверждённому дизайну (ui_visual_tokens.json):
- боковая панель width ~220px, bg SIDEBAR_BG
- логотип приложения вверху
- активная секция подсветка border_focus
- три основных раздела + история внизу
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ui.theme import (
    ACCENT, BORDER_SUBTLE, DIM, FG, FONT_APP_TITLE, FONT_BODY, FONT_H2,
    FONT_SECONDARY, GOOD, RADIUS_CARD,
    SIDEBAR_BG, SURFACE_1, SURFACE_HOVER, SPACE_M, SPACE_XS,
    TEXT_MUTED, TEXT_PRIMARY,
)


class Navigation(tk.Frame):
    """Вертикальная навигация слева с тремя разделами.

    Возвращает выбранный раздел через callback `on_select(section_name)`.
    """

    def __init__(self, master, on_select, width=220, **kwargs):
        super().__init__(master, bg=SIDEBAR_BG, width=width, **kwargs)
        self._on_select = on_select
        self._active = None
        self._buttons = {}
        self.pack_propagate(False)

        # Логотип / название приложения
        self._build_header()

        # Разделы
        self._build_section("Главная", "🏠")
        self._build_section("Голоса", "🎙️")
        self._build_section("Настройки", "⚙️")

        # Разделитель
        self._build_separator()

        # История и фразы — дополнительный раздел внизу
        self._build_section("История и фразы", "📜")

        # Локальная обработка (без сторонних зависимостей)
        self._build_footer()

    def _build_header(self):
        header = tk.Frame(self, bg=SIDEBAR_BG)
        header.pack(fill="x", padx=SPACE_M, pady=(SPACE_M, SPACE_M))

        tk.Label(
            header, text="RedZ", bg=SIDEBAR_BG, fg=ACCENT,
            font=FONT_APP_TITLE, anchor="w").pack(side="left")
        tk.Label(
            header, text="Voice Studio", bg=SIDEBAR_BG, fg=TEXT_PRIMARY,
            font=FONT_H2, anchor="w").pack(side="left", padx=(2, 0))

    def _build_section(self, name: str, icon: str):
        btn = tk.Button(
            self, text=f"  {icon}  {name}",
            bg=SIDEBAR_BG, fg=TEXT_MUTED, activebackground=SURFACE_HOVER,
            activeforeground=TEXT_PRIMARY, font=FONT_BODY,
            relief="flat", anchor="w", cursor="hand2",
            padx=SPACE_M, pady=SPACE_XS,
            highlightthickness=0, bd=0)
        btn.pack(fill="x", padx=SPACE_M, pady=1)

        # Hover
        btn.bind("<Enter>", lambda e, b=btn: self._hover(b, True))
        btn.bind("<Leave>", lambda e, b=btn: self._hover(b, False))
        btn.bind("<Button-1>", lambda e: self.select(name))

        self._buttons[name] = btn

    def _build_separator(self):
        sep = tk.Frame(self, bg=BORDER_SUBTLE, height=1)
        sep.pack(fill="x", padx=SPACE_M, pady=SPACE_M)

    def _build_footer(self):
        footer = tk.Frame(self, bg=SIDEBAR_BG)
        footer.pack(fill="x", padx=SPACE_M, pady=(SPACE_M, 0))

        tk.Label(
            footer, text="ИСТОРИЯ И ФРАЗЫ", bg=SIDEBAR_BG, fg=TEXT_MUTED,
            font=FONT_SECONDARY, anchor="w").pack(anchor="w")
        tk.Label(
            footer, text="Открыть историю →", bg=SIDEBAR_BG, fg=ACCENT,
            font=FONT_BODY, anchor="w", cursor="hand2").pack(
                anchor="w", pady=(SPACE_XS, 0))

        spacer = tk.Frame(self, bg=SIDEBAR_BG)
        spacer.pack(fill="both", expand=True)

        tk.Label(
            footer, text="LOCAL PROCESSING", bg=SIDEBAR_BG, fg=GOOD,
            font=FONT_SECONDARY, anchor="w").pack(anchor="w")

    def _hover(self, btn, hovered: bool):
        if hovered:
            btn.configure(bg=SURFACE_HOVER, fg=TEXT_PRIMARY)
        else:
            active = (self._active == btn.cget("text").split()[-1]
                      if btn.cget("text") else False)
            btn.configure(
                bg=SURFACE_HOVER if active else SIDEBAR_BG,
                fg=TEXT_PRIMARY if active else TEXT_MUTED)

    def select(self, name: str):
        """Выбрать раздел по имени."""
        if name == self._active:
            return
        self._active = name
        for n, btn in self._buttons.items():
            is_active = (n == name)
            btn.configure(
                bg=SURFACE_HOVER if is_active else SIDEBAR_BG,
                fg=TEXT_PRIMARY if is_active else TEXT_MUTED)
        if self._on_select:
            self._on_select(name)
