"""Тёмная таблица для нового интерфейса.

Почему не ttk.Treeview: в системной теме Windows (vista) Treeview рисует
белое поле и светлые заголовки — стиль `fieldbackground` игнорируется.
Свой виджет на Canvas держит всю палитру приложения.

columns: список кортежей (ключ, заголовок, вес_колонки, выравнивание).
"""

from __future__ import annotations

import tkinter as tk

from ui.theme import (
    ACCENT, BORDER_SUBTLE, FONT_BODY, FONT_SECONDARY, SURFACE_1, SURFACE_2,
    SURFACE_3, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
)

ROW_H = 26


class DarkTable(tk.Frame):
    """Таблица со строками, выделением и тонкой полосой прокрутки."""

    def __init__(self, master, columns, visible_rows: int = 8,
                 bg: str = SURFACE_1, header_bg: str = SURFACE_2,
                 on_select=None, on_check=None, selectable: bool = False,
                 **kwargs):
        super().__init__(master, bg=bg, **kwargs)
        self.columns = list(columns)
        self.bg = bg
        self.header_bg = header_bg
        self.on_select = on_select
        self.on_check = on_check
        self.visible_rows = visible_rows
        self.selectable = bool(selectable)

        self._rows: list[dict] = []
        self._widgets: list[tk.Frame] = []
        self._selected: str | None = None
        self._drag_from = 0.0
        # отмеченные строки (для выбора нескольких дублей)
        self._checked: dict[str, bool] = {}

        # --- Заголовок ---
        # Ширина колонок заголовка должна совпадать с шириной строк,
        # поэтому справа резервируем место под полосу прокрутки.
        self.header_wrap = tk.Frame(self, bg=header_bg)
        self.header_wrap.pack(fill="x")
        # Сначала резервируем место под полосу прокрутки, потом —
        # заголовок занимает всю оставшуюся ширину (порядок pack важен).
        tk.Frame(self.header_wrap, bg=header_bg, width=10).pack(
            side="right", fill="y")
        self.header = tk.Frame(self.header_wrap, bg=header_bg)
        self.header.pack(side="left", fill="x", expand=True)
        for i, (_key, title, weight, _anchor) in enumerate(self.columns):
            self.header.grid_columnconfigure(i, weight=weight, minsize=48)
            lbl = tk.Label(self.header, text=title, bg=header_bg,
                           fg=TEXT_SECONDARY, font=FONT_SECONDARY,
                           anchor=_anchor, padx=8, pady=6)
            lbl.grid(row=0, column=i, sticky="ew")

        # «выбрать все» в заголовке (только если таблица с выбором)
        self._sel_all_var = tk.BooleanVar(value=False)
        if self.selectable:
            self._sel_all_var.trace_add("write", self._on_sel_all)
            chk = tk.Checkbutton(
                self.header, variable=self._sel_all_var, bg=header_bg,
                activebackground=header_bg, selectcolor=SURFACE_2,
                highlightthickness=0, bd=0)
            chk.grid(row=0, column=0, sticky="w", padx=(6, 0))

        # --- Тело ---
        body = tk.Frame(self, bg=bg)
        body.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(body, bg=bg, highlightthickness=0, bd=0,
                                takefocus=0)
        self.canvas.pack(side="left", fill="both", expand=True)

        self.sb = tk.Canvas(body, bg=bg, highlightthickness=0, bd=0,
                            width=10, takefocus=0)
        self.sb.pack(side="right", fill="y")

        self.rows_frame = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window((0, 0), window=self.rows_frame,
                                              anchor="nw")
        self.rows_frame.bind("<Configure>", self._on_rows_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        # Колесо мыши.
        #
        # ВАЖНО: раньше <MouseWheel> висел только на canvas. Курсор в
        # таблице почти всегда над rows_frame или над Label внутри строки —
        # событие до canvas не доходит, и список не прокручивался.
        # Теперь вешаем на все уровни (bind_all с проверкой, что курсор
        # внутри таблицы).
        self._wheel_bound = False
        for w in (self.canvas, self.rows_frame):
            w.bind("<Enter>", self._bind_wheel, add="+")
            w.bind("<Leave>", self._unbind_wheel, add="+")
        self.sb.bind("<Configure>", lambda e: self._update_thumb())
        self.sb.bind("<Button-1>", self._sb_press)
        self.sb.bind("<B1-Motion>", self._sb_drag)
        self.sb.bind("<ButtonRelease-1>", lambda e: None)

    # ---------- колесо мыши ----------
    def _bind_wheel(self, _event=None):
        if self._wheel_bound:
            return
        self.canvas.bind_all("<MouseWheel>", self._on_wheel, add="+")
        # Linux/X11
        self.canvas.bind_all("<Button-4>", self._on_wheel_linux, add="+")
        self.canvas.bind_all("<Button-5>", self._on_wheel_linux, add="+")
        self._wheel_bound = True

    def _unbind_wheel(self, _event=None):
        if not self._wheel_bound:
            return
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            try:
                self.canvas.unbind_all(seq)
            except Exception:
                pass
        self._wheel_bound = False

    def _on_wheel(self, event):
        # Прокручиваем только если курсор внутри таблицы
        try:
            w = self.winfo_containing(event.x_root, event.y_root)
        except Exception:
            w = None
        if w is None:
            return
        # поднимаемся к self, если это не наш виджет
        try:
            cur = w
            while cur is not None:
                if cur is self or cur is self.canvas or cur is self.rows_frame:
                    break
                cur = getattr(cur, "master", None)
            else:
                return
        except Exception:
            pass
        delta = int(getattr(event, "delta", 0))
        if delta:
            self.canvas.yview_scroll(-int(delta / 120) * 3, "units")
            self._update_thumb()

    def _on_wheel_linux(self, event):
        if getattr(event, "num", 0) == 4:
            self.canvas.yview_scroll(-3, "units")
        elif getattr(event, "num", 0) == 5:
            self.canvas.yview_scroll(3, "units")
        self._update_thumb()

    # ---------- данные ----------
    @property
    def rows(self) -> list[dict]:
        """Текущие строки таблицы."""
        return self._rows

    def set_rows(self, rows: list[dict]):
        """rows: список словарей {ключ_колонки: текст, '_id': идентификатор}."""
        self._rows = list(rows)
        for w in self._widgets:
            w.destroy()
        self._widgets = []
        for row in self._rows:
            self._widgets.append(self._make_row(row))
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self._update_thumb()

    def _make_row(self, row: dict) -> tk.Frame:
        rid = str(row.get("_id", ""))
        frame = tk.Frame(self.rows_frame, bg=self.bg)
        frame.grid_columnconfigure(0, weight=1)
        col = 0
        if self.selectable:
            # колонка выбора
            frame.grid_columnconfigure(0, weight=0, minsize=26)
            var = tk.BooleanVar(value=bool(self._checked.get(rid, False)))
            chk = tk.Checkbutton(
                frame, variable=var, bg=self.bg,
                activebackground=self.bg, selectcolor=SURFACE_2,
                highlightthickness=0, bd=0)
            chk.grid(row=0, column=col, sticky="w", padx=(6, 0))
            var.trace_add("write", lambda *_a, r=rid, v=var: self._on_check(r, v))
            frame._check_var = var
            col += 1
        for i, (key, _title, weight, anchor) in enumerate(self.columns):
            frame.grid_columnconfigure(col, weight=weight, minsize=48)
            lbl = tk.Label(frame, text=str(row.get(key, "")), bg=self.bg,
                           fg=TEXT_PRIMARY, font=FONT_BODY, anchor=anchor,
                           padx=8, pady=4, height=1)
            lbl.grid(row=0, column=col, sticky="ew")
            lbl.bind("<Button-1>", lambda e, r=rid: self._select(r))
            frame.bind("<Button-1>", lambda e, r=rid: self._select(r))
            col += 1
        frame.bind("<Configure>", lambda e, f=frame: None)
        frame.pack(fill="x")
        self._sync_height(frame)
        return frame

    def _on_check(self, rid: str, var) -> None:
        """Отметка строки изменилась."""
        try:
            val = bool(var.get())
        except Exception:
            val = False
        self._checked[rid] = val
        if self.on_check:
            try:
                self.on_check(rid, val)
            except Exception:
                pass

    def _on_sel_all(self, *_args) -> None:
        """Отметить/снять все строки."""
        try:
            want = bool(self._sel_all_var.get())
        except Exception:
            return
        for row, widget in zip(self._rows, self._widgets):
            rid = str(row.get("_id", ""))
            self._checked[rid] = want
            var = getattr(widget, "_check_var", None)
            if var is not None:
                try:
                    var.set(want)
                except Exception:
                    pass

    def checked_ids(self) -> list[str]:
        """Отмеченные строки (id)."""
        return [rid for rid, on in self._checked.items() if on]

    def clear_checked(self) -> None:
        """Снять все отметки."""
        for rid in list(self._checked.keys()):
            self._checked[rid] = False
        for widget in self._widgets:
            var = getattr(widget, "_check_var", None)
            if var is not None:
                try:
                    var.set(False)
                except Exception:
                    pass
        try:
            self._sel_all_var.set(False)
        except Exception:
            pass

    def _sync_height(self, frame: tk.Frame):
        try:
            frame.configure(height=ROW_H)
        except tk.TclError:
            pass

    def clear(self):
        self.set_rows([])

    # ---------- выделение ----------
    def _select(self, rid: str, notify: bool = True):
        self._selected = rid
        for row, widget in zip(self._rows, self._widgets):
            active = str(row.get("_id", "")) == rid
            bg = SURFACE_3 if active else self.bg
            fg = TEXT_PRIMARY
            widget.configure(bg=bg)
            for child in widget.winfo_children():
                child.configure(bg=bg, fg=fg)
        if notify and self.on_select:
            self.on_select(rid)

    def select(self, rid: str, notify: bool = True):
        """Выделить строку по идентификатору."""
        self._select(str(rid), notify)

    @property
    def selected(self) -> str | None:
        return self._selected

    def selected_row(self) -> dict | None:
        for row in self._rows:
            if str(row.get("_id", "")) == str(self._selected):
                return row
        return None

    # ---------- прокрутка ----------
    def _on_rows_configure(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self._update_thumb()

    def _on_canvas_configure(self, event):
        self.canvas.itemconfigure(self._win, width=event.width)
        self._update_thumb()

    def _update_thumb(self):
        """Положение ползунка полосы прокрутки."""
        try:
            self.sb.delete("all")
            h = self.sb.winfo_height()
            w = self.sb.winfo_width()
            if h <= 1:
                return
            first, last = self.canvas.yview()
            total = max(1.0, last - first)
            visible = max(0.12, min(1.0, 1.0 / total))
            y0 = first / total * h
            y1 = y0 + visible * h
            self.sb.create_rectangle(2, y0, w - 2, min(h - 1, y1),
                                     fill=SURFACE_3, outline="")
        except (tk.TclError, ValueError, ZeroDivisionError):
            pass

    def _sb_press(self, event):
        self._drag_from = self.canvas.yview()[0]
        self._sb_move(event)

    def _sb_drag(self, event):
        self._sb_move(event)

    def _sb_move(self, event):
        try:
            h = self.sb.winfo_height()
            if h <= 1:
                return
            first, last = self.canvas.yview()
            total = max(1e-6, last - first)
            frac = min(1.0, max(0.0, event.y / h))
            self.canvas.yview_moveto(max(0.0, frac - (1.0 - 1.0 / total) / 2))
            self._update_thumb()
        except (tk.TclError, ValueError):
            pass
