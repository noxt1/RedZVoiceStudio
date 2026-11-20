"""Переиспользуемые карточки со скруглёнными углами.

Простая реализация на tk.Frame + Canvas-подложка. Canvas используется только
для рисования фона и границы, контент кладётся через pack() — это надёжно
работает и в исходниках, и в собранном EXE.
"""

from __future__ import annotations

import tkinter as tk

from ui.theme import (
    BORDER_SUBTLE, GOOD, HOVER, RADIUS_CARD,
    SURFACE_1, SURFACE_HOVER, SURFACE_PRESSED, SPACE_M, SPACE_S,
    TEXT_MUTED, WARN,
)


def _patch_canvas() -> None:
    """Добавить create_round_rect к tk.Canvas (если ещё не добавлен)."""
    if hasattr(tk.Canvas, "_redz_round_rect_patched"):
        return
    tk.Canvas._redz_round_rect_patched = True

    def _create_round_rect(self, x1, y1, x2, y2, r, **kwargs):
        points = [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
        ]
        return self.create_polygon(points, smooth=True, **kwargs)

    tk.Canvas.create_round_rect = _create_round_rect


_patch_canvas()


class GlassCard(tk.Frame):
    """Карточка со скруглёнными углами и мягкой границей.

    Параметры:
        master — родительский виджет.
        radius — радиус скругления (по умолчанию RADIUS_CARD).
        bg — цвет фона карточки (по умолчанию SURFACE_1).
        border — цвет границы (по умолчанию BORDER_SUBTLE).
        pad — внутренний отступ от краёв карточки до содержимого.
    """

    def __init__(self, master, radius=RADIUS_CARD, bg=SURFACE_1,
                 border=BORDER_SUBTLE, pad=SPACE_M, **kwargs):
        super().__init__(master, bg=bg, highlightthickness=0, bd=0, **kwargs)
        self._radius = radius
        self._bg = bg
        self._border = border
        self._pad = pad
        self._hover = False
        self._destroyed = False

        # Canvas-подложка для фона и границы
        self._canvas = tk.Canvas(self, highlightthickness=0, bd=0, bg=bg)
        self._canvas.place(x=0, y=0, relwidth=1, relheight=1)

        # Внутренний контейнер для содержимого
        self._inner = tk.Frame(self, bg=bg)
        self._inner.pack(fill="both", expand=True, padx=pad, pady=pad)

        self.bind("<Configure>", self._on_resize)
        self._draw()

    # ---------- отрисовка ----------

    def _draw(self):
        """Нарисовать скруглённый прямоугольник с границей."""
        if self._destroyed:
            return
        try:
            self._canvas.delete("all")
        except tk.TclError:
            self._destroyed = True
            return
        w = self.winfo_width()
        h = self.winfo_height()
        if w <= 1 or h <= 1:
            return
        r = min(self._radius, w // 2, h // 2)

        # Фон карточки
        self._canvas.create_round_rect(
            0, 0, w, h, r, fill=self._bg, outline="")
        # Граница
        self._canvas.create_round_rect(
            0, 0, w, h, r, fill="", outline=self._border, width=1)

    def _on_resize(self, _event=None):
        if self._destroyed:
            return
        try:
            self._draw()
        except tk.TclError:
            self._destroyed = True

    # ---------- API ----------

    def set_focus(self, focused: bool = True):
        """Показать/скрыть подсветку границы (фокус)."""
        if self._destroyed:
            return
        self._canvas.create_round_rect(
            0, 0, self.winfo_width(), self.winfo_height(),
            min(self._radius, self.winfo_width() // 2, self.winfo_height() // 2),
            fill="", outline="#6CBDEB" if focused else self._border, width=1)

    def set_hover(self, hovered: bool = True):
        """Подсветка при наведении мыши."""
        if self._destroyed:
            return
        self._hover = hovered
        color = SURFACE_HOVER if hovered else self._bg
        try:
            self.configure(bg=color)
            self._inner.configure(bg=color)
        except tk.TclError:
            pass
        self._draw()

    @property
    def inner(self) -> tk.Frame:
        """Внутренний контейнер для размещения содержимого."""
        return self._inner

    @property
    def canvas(self) -> tk.Canvas:
        """Canvas карточки (для кастомной отрисовки внутри)."""
        return self._canvas

    def destroy(self):
        self._destroyed = True
        super().destroy()
