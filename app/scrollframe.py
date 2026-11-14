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
        # колесо мыши: прокрутка при курсере над содержимым
        self.body.bind("<Enter>", self._bind_wheel)
        self.body.bind("<Leave>", self._unbind_wheel)
        for widget in (self.canvas,):
            widget.bind("<Enter>", self._bind_wheel)
            widget.bind("<Leave>", self._unbind_wheel)

    # ---------- размеры ----------
    def _on_body(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas(self, event) -> None:
        # ширина внутреннего фрейма = ширина окна (иначе содержимое
        # не растягивается, а полоса прокрутки прыгает)
        self.canvas.itemconfigure(self._win, width=event.width)

    # ---------- колесо мыши ----------
    def _bind_wheel(self, _event=None) -> None:
        self.canvas.bind_all("<MouseWheel>", self._on_wheel, add="+")

    def _unbind_wheel(self, _event=None) -> None:
        try:
            self.canvas.unbind_all("<MouseWheel>")
        except Exception:
            pass

    def _on_wheel(self, event) -> None:
        try:
            delta = int(event.delta)
        except Exception:
            return
        # прокручиваем на 3 строки (120 = одно деление колеса)
        self.canvas.yview_scroll(-int(delta / 40) * 3, "units")

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
