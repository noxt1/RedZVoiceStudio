"""Патч: проценты прогресса, детектор зависания, остановка с отчётом.

Что добавляется:
  * в прогрессе видны проценты: «7 / 33  (21%)»;
  * если движок молчит дольше порога — панель пишет «возможно зависание»
    и показывает, сколько секунд нет ответа;
  * при долгом молчании задача снимается сама, а пользователь может
    остановить её вручную кнопкой «■ Отменить» — в обоих случаях
    пишется отчёт: что сделано, что осталось, где логи.

    python tools\\patch_stall_report.py
"""

from __future__ import annotations

import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PANEL = os.path.join(ROOT, "app", "logpanel.py")
GUI = os.path.join(ROOT, "app", "voice_studio.py")
CORE = os.path.join(ROOT, "app", "studio_core.py")

HANG_WARN_SEC = 100     # столько секунд без ответа -> предупреждение
HANG_AUTO_STOP_SEC = 420  # столько секунд без ответа -> автостоп


def patch_panel() -> None:
    with io.open(PANEL, encoding="utf-8") as fh:
        src = fh.read()

    old = '''    def progress_set(self, done: int, total: int | None = None) -> None:
        self._done = done
        if total is not None:
            self._total = total
        pct = int(self._done * 100 / self._total) if self._total else 0
        self.progress["value"] = pct
        self.progress_lbl.config(
            text=f"{self._done} / {self._total}  ({pct}%)" if self._total
            else f"{self._done} готово")
'''
    new = '''    def progress_set(self, done: int, total: int | None = None) -> None:
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
'''
    if old not in src:
        print("panel: progress_set не найден")
    else:
        src = src.replace(old, new, 1)

    old2 = '''        self._started = 0.0
        self._busy = False
'''
    new2 = '''        self._started = 0.0
        self._busy = False
        self._stalled = False
'''
    if old2 in src:
        src = src.replace(old2, new2, 1)

    old3 = '''        self._started = time.time()
        self._busy = True
'''
    new3 = '''        self._started = time.time()
        self._busy = True
        self._stalled = False
'''
    if old3 in src:
        src = src.replace(old3, new3, 1)

    with io.open(PANEL, "w", encoding="utf-8") as fh:
        fh.write(src)
    print("panel: проценты и предупреждение о зависании")


def patch_core() -> None:
    with io.open(CORE, encoding="utf-8") as fh:
        src = fh.read()

    old = '''def distribute() -> dict:'''
    new = '''def write_report(title: str, done_ids: list[str], total_ids: list[str],
                 seconds: float, reason: str) -> str:
    """Отчёт о прерванной/завершённой задаче -> workspace\\logs."""
    import datetime
    logs = os.path.join(sp.workspace(), "logs")
    os.makedirs(logs, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = os.path.join(logs, f"report_{stamp}.txt")

    done_set = set(done_ids)
    missing = [i for i in total_ids if i not in done_set]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"Задача: {title}\\n")
        fh.write(f"Итог: {reason}\\n")
        fh.write(f"Длительность: {seconds:.1f} с\\n")
        fh.write(f"Готово: {len(done_set)} из {len(total_ids)}\\n")
        if missing:
            fh.write("Не озвучено: " + ", ".join(missing) + "\\n")
        fh.write(f"Отчёт сохранён: {path}\\n")
    return path


def distribute() -> dict:'''
    if old not in src:
        print("core: distribute не найден")
    else:
        src = src.replace(old, new, 1)
        with io.open(CORE, "w", encoding="utf-8") as fh:
            fh.write(src)
        print("core: добавлена запись отчёта")


def patch_gui() -> None:
    with io.open(GUI, encoding="utf-8") as fh:
        src = fh.read()

    # 1) следить за временем последней строки от движка
    old = '''    def _handle_line(self, line: str) -> None:
        """Одна строка вывода движка -> обновление панели задачи."""
        panel = self._active_panel()
        if panel is None:
            return
'''
    new = '''    def _handle_line(self, line: str) -> None:
        """Одна строка вывода движка -> обновление панели задачи."""
        self._last_line_at = time.time()
        panel = self._active_panel()
        if panel is None:
            return
'''
    if old not in src:
        print("gui: _handle_line не найден")
    else:
        src = src.replace(old, new, 1)

    # 2) heartbeat: детектор зависания + автостоп
    old2 = '''    def _heartbeat(self) -> None:
        """Пока задача идёт — показываем, что процесс жив и сколько прошло."""
        if self.busy:
            panel = getattr(self, "_current_panel", None)
            if panel is not None:
                panel.heartbeat()
        self.root.after(1000, self._heartbeat)
'''
    new2 = '''    def _heartbeat(self) -> None:
        """Пока задача идёт — показываем, что процесс жив и сколько прошло.

        Если движок молчит дольше HANG_WARN_SEC — предупреждаем.
        Если молчит дольше HANG_AUTO_STOP_SEC — снимаем задачу сами и пишем отчёт.
        """
        if self.busy:
            panel = getattr(self, "_current_panel", None)
            if panel is not None:
                panel.heartbeat()
            silent = time.time() - getattr(self, "_last_line_at", time.time())
            if silent > HANG_AUTO_STOP_SEC:
                self._stop_job("движок не отвечает")
            elif silent > HANG_WARN_SEC:
                if panel is not None:
                    panel.stall_warning(int(silent))
        self.root.after(1000, self._heartbeat)
'''
    if old2 not in src:
        print("gui: _heartbeat не найден")
    else:
        src = src.replace(old2, new2, 1)

    # 3) отмена -> отчёт
    old3 = '''    def _cancel_job(self) -> None:
        import studio_core as core
        if not self.busy:
            self.phrase_status.config(text="Нечего отменять")
            return
        ok = core.cancel_job()
        self.phrase_status.config(text="Задача отменена" if ok else "Нечего отменять")
'''
    new3 = '''    def _cancel_job(self) -> None:
        if not self.busy:
            self.phrase_status.config(text="Нечего отменять")
            return
        self._stop_job("остановлено вручную")

    def _stop_job(self, reason: str) -> None:
        """Остановить задачу и написать отчёт: что сделано, что осталось."""
        import studio_core as core
        core.cancel_job()
        panel = getattr(self, "_current_panel", None)
        done = sorted(getattr(self, "_done_ids", []))
        total = [p["id"] for p in getattr(self, "_job_phrase_ids", [])]
        seconds = time.time() - getattr(self, "_job_started", time.time())
        path = ""
        try:
            path = core.write_report(
                getattr(self, "_job_title", "задача"), done, total, seconds, reason)
        except Exception as exc:  # noqa: BLE001
            path = f"(отчёт не записан: {exc})"
        msg = (f"{reason}. Готово {len(done)} из {len(total)}. Отчёт: {path}")
        self.phrase_status.config(text=msg[:120])
        if panel is not None:
            panel.log("warn", msg)
            for i, st in enumerate(panel._steps):
                if st["status"] in ("todo", "doing"):
                    panel.step(i, "fail", reason)
            panel.finish(False, msg[:80])
        self.busy = False
'''
    if old3 not in src:
        print("gui: _cancel_job не найден")
    else:
        src = src.replace(old3, new3, 1)

    # 4) состояние задачи: список id и отметки выполненных
    old4 = '''        self._job_total = total
        if panel is not None:
            panel.begin(title, steps or ["Выполнение"], total)
'''
    new4 = '''        self._job_total = total
        self._job_title = title
        self._job_started = time.time()
        self._last_line_at = time.time()
        self._done_ids = []
        self._job_phrase_ids = list(getattr(self, "_job_phrase_ids", []))
        if panel is not None:
            panel.begin(title, steps or ["Выполнение"], total)
'''
    if old4 not in src:
        print("gui: начало _run_job не найдено")
    else:
        src = src.replace(old4, new4, 1)

    # 5) отмечать выполненные фразы
    old5 = '''            panel.set_stage(1, f"{lid}: {text.strip()[:34]}")
'''
    new5 = '''            if lid not in self._done_ids:
                self._done_ids.append(lid)
            panel.set_stage(1, f"{lid}: {text.strip()[:34]}")
'''
    if old5 not in src:
        print("gui: отметка прогресса не найдена")
    else:
        src = src.replace(old5, new5, 1)

    # 6) константы порогов
    old6 = '''BG = "#14161a"'''
    new6 = '''HANG_WARN_SEC = 100      # столько секунд без ответа движка -> предупреждение
HANG_AUTO_STOP_SEC = 420  # столько секунд без ответа -> автостоп с отчётом

BG = "#14161a"'''
    if old6 in src:
        src = src.replace(old6, new6, 1)

    # 7) сохранять список фраз задачи (для отчёта)
    old7 = '''        self._job_total = len(payload)

        def _job(cb):'''
    new7 = '''        self._job_total = len(payload)
        self._job_phrase_ids = [{"id": p["id"]} for p in payload]

        def _job(cb):'''
    if old7 in src:
        src = src.replace(old7, new7, 1)

    with io.open(GUI, "w", encoding="utf-8") as fh:
        fh.write(src)
    print("gui: проценты, детектор зависания и отчёт при остановке")


if __name__ == "__main__":
    patch_panel()
    patch_core()
    patch_gui()
