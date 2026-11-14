"""Переиспользуемые карточки со скруглёнными углами (Canvas).

Карточка — это tk.Frame с Canvas подложкой, на которой рисуются
скруглённые углы и мягкая граница. Поддерживает hover-эффект.

Исправления Этап 5 (жизненный цикл Canvas):
- Отслеживание состояния уничтоженного виджета (_destroyed).
- Отписка от событий <Configure> и <Destroy>.
- Отмена ожидающих after_callbacks через after_cancel.
- Проверка существования виджетов перед обращением к Canvas.
- Исключение отрисовки после уничтожения карточки.
- Нет пустых except — неизвестные исключения пробрасываются.
"""

from __future__ import annotations

import tkinter as tk

from ui.theme import (
    BORDER_FOCUS, BORDER_SUBTLE, GOOD, HOVER, RADIUS_CARD,
    SURFACE_1, SURFACE_HOVER, SURFACE_PRESSED, SPACE_M, SPACE_S,
    TEXT_MUTED, WARN,
)


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
        super().__init__(master, bg=bg, **kwargs)
        self._radius = radius
        self._bg = bg
        self._border = border
        self._pad = pad
        self._hover = False
        self._border_focus = False
        self._destroyed = False
        self._redraw_job = None

        # Canvas для рисования фона и границы — лежит под содержимым
        self._canvas = tk.Canvas(
            self, highlightthickness=0, bd=0, bg=bg)
        self._canvas.place(x=0, y=0, relwidth=1, relheight=1)

        # Внутренний контейнер для содержимого (с отступами)
        self._inner = tk.Frame(self, bg=bg)
        self._inner.place(
            x=pad, y=pad,
            width=-2 * pad, height=-2 * pad,
            anchor="nw")

        # Перерисовка при изменении размера
        self.bind("<Configure>", self._on_resize)
        self._inner.bind("<Configure>", lambda _e: self._on_resize(None))
        # Отписка при уничтожении — критично для Этап 5
        self.bind("<Destroy>", self._on_destroy)

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

        # Тень (лёгкая, через Canvas — никаких внешних зависимостей)
        self._canvas.create_rectangle(
            3, 3, w - 3, h - 3, fill="#050709", outline="", width=0)

        # Фон карточки
        self._canvas.create_round_rect(
            0, 0, w, h, r, fill=self._bg, outline="")

        # Граница
        border_color = BORDER_FOCUS if self._border_focus else self._border
        self._canvas.create_round_rect(
            0, 0, w, h, r, fill="", outline=border_color, width=1)

    def _on_destroy(self, event):
        """Обработка уничтожения виджета — Этап 5 требование."""
        if event.widget is not self:
            return
        self._destroyed = True
        # Отменяем ожидающий перерисовку
        if self._redraw_job is not None:
            try:
                self.after_cancel(self._redraw_job)
            except tk.TclError:
                pass
            self._redraw_job = None
        # Отписываемся от событий
        try:
            self.unbind("<Configure>")
        except tk.TclError:
            pass
        try:
            self.unbind("<Destroy>")
        except tk.TclError:
            pass
        try:
            self._inner.unbind("<Configure>")
        except tk.TclError:
            pass

    def _on_resize(self, _event):
        """Перерисовка при изменении размера — с защитой от уничтожения."""
        if self._destroyed:
            return
        # Отменяем старую отложенную перерисовку, если есть
        if self._redraw_job is not None:
            try:
                self.after_cancel(self._redraw_job)
            except tk.TclError:
                pass
        try:
            self._redraw_job = self.after_idle(self._draw)
        except tk.TclError:
            self._redraw_job = None

    # ---------- API ----------

    def set_focus(self, focused: bool = True):
        """Показать/скрыть подсветку границы (фокус)."""
        if self._destroyed:
            return
        self._border_focus = focused
        self._draw()

    def set_hover(self, hovered: bool = True):
        """Подсветка при наведении мыши."""
        if self._destroyed:
            return
        self._hover = hovered
        if hovered:
            self.configure(bg=SURFACE_HOVER)
            self._inner.configure(bg=SURFACE_HOVER)
        else:
            self.configure(bg=self._bg)
            self._inner.configure(bg=self._bg)
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
        """Безопасное уничтожение с очисткой колбэков — Этап 5."""
        self._destroyed = True
        if self._redraw_job is not None:
            try:
                self.after_cancel(self._redraw_job)
            except tk.TclError:
                pass
            self._redraw_job = None
        super().destroy()


# ---------------------------------------------------------------------------
# Расширение Canvas: метод create_round_rect
# ---------------------------------------------------------------------------

def _patch_canvas():
    """Добавить метод create_round_rect к tk.Canvas (если ещё не добавлен)."""
    if hasattr(tk.Canvas, "_redz_round_rect_patched"):
        return
    tk.Canvas._redz_round_rect_patched = True

    def _create_round_rect(self, x1, y1, x2, y2, r, **kwargs):
        points = [
            x1 + r, y1,
            x2 - r, y1,
            x2, y1,
            x2, y1 + r,
            x2, y2 - r,
            x2, y2,
            x2 - r, y2,
            x1 + r, y2,
            x1, y2,
            x1, y2 - r,
            x1, y1 + r,
            x1, y1,
        ]
        return self.create_polygon(points, smooth=True, **kwargs)

    tk.Canvas.create_round_rect = _create_round_rect


_patch_canvas()
