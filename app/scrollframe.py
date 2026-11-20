"""Прокручиваемый контейнер для вкладок.

Зачем: живой перевод — самая длинная вкладка, и без прокрутки блок
«В игре» (оверлей, слышимость, перехват игроков) уезжает за нижний край
окна на мониторах 1080p. Здесь контент кладётся в Canvas и прокручивается
колесом мыши и ползунком.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class ScrollFrame(ttk.Frame):
    """Фрейм, внутри которого всё прокручивается по вертикали."""

    def __init__(self, parent, bg: str = "#14161a", **kw) -> None:
        super().__init__(parent, **kw)
        self.bg = bg
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0,
                                bd=0, takefocus=0)
        self.scroll = ttk.Scrollbar(self, orient="vertical",
                                    command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scroll.grid(row=0, column=1, sticky="ns")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        # содержимое живёт внутри Canvas
        self.body = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window((0, 0), window=self.body,
                                              anchor="nw")
        self.body.bind("<Configure>", self._on_body)
        self.canvas.bind("<Configure>", self._on_canvas)

        # Колесо мыши.
        #
        # ВАЖНО: раньше здесь был bind_all — глобальный перехват. При
        # нескольких ScrollFrame на одном окне (в «Голосах» их три) последний
        # созданный перебивал остальные, и прокрутка работала только в
        # одной под-вкладке. Теперь вешаем на конкретные виджеты.
        for widget in (self.canvas, self.body):
            widget.bind("<Enter>", self._bind_wheel, add="+")
            widget.bind("<Leave>", self._unbind_wheel, add="+")
        self._wheel_bound = False

        # Windows: колесо отдаёт delta, Linux — Button-4/5
        self.canvas.bind("<Button-4>", self._on_wheel_linux, add="+")
        self.canvas.bind("<Button-5>", self._on_wheel_linux, add="+")

    # ---------- размеры ----------
    def _on_body(self, _event=None) -> None:
        # Пересчёт scrollregion только если содержимое реально изменилось.
        # Раньше это делалось на каждый <Configure> — при переключении
        # вкладок Tk успевал отрисовать пустой кадр, отсюда «прогрузка».
        try:
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        except Exception:
            pass

    def _on_canvas(self, event) -> None:
        # Ширина внутреннего фрейма = ширина видимой области canvas.
        # Проверяем, изменилась ли ширина: если нет — ничего не делаем,
        # иначе идёт лишний пересчёт раскладки.
        try:
            cur = self.canvas.itemcget(self._win, "width")
        except Exception:
            cur = None
        try:
            cur_w = int(float(cur)) if cur not in (None, "") else 0
        except Exception:
            cur_w = 0
        if cur_w == int(event.width):
            return
        self.canvas.itemconfigure(self._win, width=event.width)

    # ---------- колесо мыши ----------
    def _bind_wheel(self, _event=None) -> None:
        if self._wheel_bound:
            return
        self.canvas.bind_all("<MouseWheel>", self._on_wheel, add="+")
        self._wheel_bound = True

    def _unbind_wheel(self, _event=None) -> None:
        if not self._wheel_bound:
            return
        try:
            self.canvas.unbind_all("<MouseWheel>")
        except Exception:
            pass
        self._wheel_bound = False

    def _on_wheel(self, event) -> None:
        try:
            delta = int(event.delta)
        except Exception:
            return
        if delta == 0:
            return
        # Windows: 120 = одно деление колеса. Прокручиваем на 3 строки.
        self.canvas.yview_scroll(-int(delta / 40) * 3, "units")

    def _on_wheel_linux(self, event) -> None:
        # Linux/X11: Button-4 = вверх, Button-5 = вниз
        if getattr(event, "num", 0) == 4:
            self.canvas.yview_scroll(-3, "units")
        elif getattr(event, "num", 0) == 5:
            self.canvas.yview_scroll(3, "units")

    # ---------- переход к элементу ----------
    def scroll_to(self, widget) -> None:
        """Прокрутить так, чтобы видно было элемент."""
        try:
            self.canvas.update_idletasks()
            y = widget.winfo_rooty() - self.body.winfo_rooty()
            total = max(1, self.body.winfo_height())
            frac = max(0.0, min(1.0, y / total))
            self.canvas.yview_moveto(frac)
        except Exception:
            pass
