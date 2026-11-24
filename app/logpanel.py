"""Панель задачи: видно, на каком этапе кнопка и выполнено ли.

Показывает:
  * название задачи
  * список шагов с состояниями (ожидает / в работе / готово / ошибка)
  * прогресс-бар и счётчик «готово / всего»
  * подробный журнал строк
"""

from __future__ import annotations

import time
import tkinter as tk
from tkinter import ttk

BG = "#14161a"
FG = "#e8e8e8"
DIM = "#8b93a1"
ACCENT = "#4a9eff"
GOOD = "#7bd88f"
BAD = "#e88a8a"
WARN = "#e8c07a"

TODO, DOING, DONE, FAIL = "todo", "doing", "done", "fail"

MARKS = {TODO: "·", DOING: "▸", DONE: "✓", FAIL: "✗"}
COLORS = {TODO: DIM, DOING: ACCENT, DONE: GOOD, FAIL: BAD}


class LogPanel(tk.Frame):
    """Виджет: шаги задачи + прогресс + журнал."""

    def __init__(self, parent, height_steps: int = 6, height_log: int = 8):
        super().__init__(parent, bg=BG)

        self.title_lbl = tk.Label(self, text="", bg=BG, fg=FG,
                                  font=("Segoe UI", 11, "bold"), anchor="w")
        self.title_lbl.pack(fill="x", padx=2, pady=(2, 2))

        self.progress = ttk.Progressbar(self, maximum=100, length=200)
        self.progress.pack(side="left", padx=(2, 8), pady=(0, 4))
        try:
            style = ttk.Style(self)
            style.configure("Auraloom.Horizontal.TProgressbar", troughcolor="#1e2229",
                            background=ACCENT, bordercolor="#1e2229",
                            lightcolor=ACCENT, darkcolor=ACCENT,
                            thickness=12, borderwidth=0)
            self.progress.configure(style="Auraloom.Horizontal.TProgressbar")
        except tk.TclError:
            pass
        self.progress_lbl = tk.Label(self, text="", bg=BG, fg=DIM,
                                      font=("Segoe UI", 9))
        self.progress_lbl.pack(side="left", pady=(0, 4))

        # --- шаги ---
        steps_frame = tk.LabelFrame(self, text=" Шаги ", bg=BG, fg=DIM,
                                    font=("Segoe UI", 9), padx=10, pady=6)
        steps_frame.pack(fill="x", padx=2, pady=(4, 4))
        self.steps_text = tk.Text(steps_frame, bg=BG, fg=FG, relief="flat",
                                  font=("Consolas", 9), height=height_steps,
                                  wrap="none")
        self.steps_text.pack(fill="both", expand=True)
        self.steps_text.configure(state="disabled")
        for tag, color in COLORS.items():
            self.steps_text.tag_configure(tag, foreground=color)

        # --- журнал ---
        log_frame = tk.LabelFrame(self, text=" Журнал ", bg=BG, fg=DIM,
                                  font=("Segoe UI", 9), padx=10, pady=6)
        log_frame.pack(fill="both", expand=True, padx=2, pady=(4, 2))
        self.log_text = tk.Text(log_frame, bg="#1e2229", fg="#c8cedb", relief="flat",
                                font=("Consolas", 9), height=height_log, wrap="none")
        self.log_text.pack(fill="both", expand=True)
        self.log_text.configure(state="disabled")
        self.log_text.tag_configure("ok", foreground=GOOD)
        self.log_text.tag_configure("bad", foreground=BAD)
        self.log_text.tag_configure("warn", foreground=WARN)
        self.log_text.tag_configure("dim", foreground=DIM)
        self.log_text.tag_configure("head", foreground=ACCENT)

        self._steps: list[dict] = []
        self._done = 0
        self._total = 0
        self._started = 0.0
        self._busy = False
        self._stalled = False

    # ---------- состояние ----------
    def begin(self, title: str, steps: list[str], total: int = 0) -> None:
        self._steps = [{"title": s, "status": TODO, "detail": ""} for s in steps]
        self._done = 0
        self._total = total
        self._started = time.time()
        self._busy = True
        self._stalled = False
        self.title_lbl.config(text=title, fg=ACCENT)
        self.progress["value"] = 0
        self.progress_lbl.config(text=f"0 / {total}" if total else "выполняется…")
        self._render_steps()
        self._clear_log()
        self.log("head", f"→ {title}")
        self.log("dim", f"шагов: {len(steps)}" + (f", фраз: {total}" if total else ""))

    def step(self, index: int, status: str, detail: str = "") -> None:
        if 0 <= index < len(self._steps):
            self._steps[index]["status"] = status
            if detail:
                self._steps[index]["detail"] = detail
            self._render_steps()

    def progress_set(self, done: int, total: int | None = None) -> None:
        self._done = done
        if total is not None:
            self._total = total
        pct = int(self._done * 100 / self._total) if self._total else 0
        self.progress["value"] = pct
        if self._total:
            self.progress_lbl.config(text=f"{self._done} / {self._total}  ({pct}%)")
        else:
            self.progress_lbl.config(text=f"{self._done} готово")

    def stall_warning(self, seconds: int) -> None:
        """Сообщить, что движок давно не отвечает."""
        if self._stalled:
            return
        self._stalled = True
        self.title_lbl.config(text=f"{self.title_lbl.cget('text')}  ·  возможно зависание", fg=WARN)
        self.log("warn", f"Нет ответа от движка уже {seconds} с — возможно зависание. "
                         f"Можно нажать «Отменить».")

    def heartbeat(self) -> None:
        """Показываем, что процесс жив: прошло времени + текущий этап."""
        if not self._busy:
            return
        elapsed = int(time.time() - self._started)
        doing = [s["title"] for s in self._steps if s["status"] == "doing"]
        stage = doing[-1] if doing else (self._steps[0]["title"] if self._steps else "")
        self.progress_lbl.config(text=f"идёт {elapsed} с  ·  этап: {stage[:32]}")
        self.title_lbl.config(text=f"{self.title_lbl.cget('text').split('  —  ')[0]}  ·  "
                                  f"работаю {elapsed} с")

    def set_stage(self, index: int, detail: str = "") -> None:
        """Перевести шаг в состояние «в работе»."""
        self.step(index, "doing", detail)

    def finish(self, ok: bool, summary: str = "") -> None:
        self._busy = False
        elapsed = time.time() - self._started
        if ok:
            self.title_lbl.config(text=f"{self.title_lbl.cget('text')} — готово", fg=GOOD)
            self.progress["value"] = 100
        else:
            self.title_lbl.config(text=f"{self.title_lbl.cget('text')} — с ошибкой", fg=BAD)
        self.log("ok" if ok else "bad",
                 f"{'Готово' if ok else 'Ошибка'} за {elapsed:.1f} c" +
                 (f": {summary}" if summary else ""))
        self._render_steps()

    def log(self, level: str, text: str) -> None:
        if not text:
            return
        stamp = time.strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"{stamp}  ", "dim")
        self.log_text.insert("end", text + "\n", level if level in
                             ("ok", "bad", "warn", "dim", "head") else "")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    # ---------- отрисовка ----------
    def _render_steps(self) -> None:
        self.steps_text.configure(state="normal")
        self.steps_text.delete("1.0", "end")
        for i, step in enumerate(self._steps):
            mark = MARKS.get(step["status"], "·")
            line = f"{mark} {step['title']}"
            if step["detail"]:
                line += f"  —  {step['detail']}"
            self.steps_text.insert("end", line + "\n", step["status"])
        self.steps_text.configure(state="disabled")

    def _clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
