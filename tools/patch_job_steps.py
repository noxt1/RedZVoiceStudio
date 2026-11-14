"""Патч: запуск задач через панель шагов (этапы видно сразу).

    python tools\\patch_job_steps.py
"""

from __future__ import annotations

import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUI = os.path.join(ROOT, "app", "voice_studio.py")

OLD_RUN = '''    def _run_job(self, title: str, job, status=None, total: int = 0) -> None:
        if self.busy:
            status = status or self.phrase_status
            status.config(text="Занято — дождись окончания текущей задачи")
            return
        self.busy = True
        target = status or self.phrase_status
        target.config(text=title)
        self.progress_lbl.config(text=f"0 / {total}" if total else "работаю…")

        def _worker():
            def cb(line: str) -> None:
                self.log_queue.put(line)

            code = job(cb)
            self.log_queue.put(f"=== завершено, код {code} ===")
            self.root.after(0, lambda: self._job_done(code, target, total))

        threading.Thread(target=_worker, daemon=True).start()

    def _job_done(self, code: int, target, total: int = 0) -> None:
        self.busy = False
        target.config(text="Готово" if code == 0 else f"Завершилось с кодом {code}")
        if total:
            self.progress_lbl.config(text=f"{total} / {total} — готово"
                                     if code == 0 else f"ошибка {code}")
        self._refresh_phrases()
'''

NEW_RUN = '''    def _run_job(self, title: str, job, status=None, total: int = 0,
                 steps: list[str] | None = None, panel=None) -> None:
        """Запустить задачу с видимыми этапами."""
        if self.busy:
            msg = "Занято — дождись окончания текущей задачи"
            (status or self.phrase_status).config(text=msg)
            (panel or getattr(self, "task_panel", None)) and (panel or self.task_panel).log("warn", msg)
            return
        self.busy = True
        target = status or self.phrase_status
        target.config(text=title)
        panel = panel or getattr(self, "task_panel", None)
        self._current_panel = panel
        self._job_total = total
        if panel is not None:
            panel.begin(title, steps or ["Выполнение"], total)

        def _worker():
            def cb(line: str) -> None:
                self.log_queue.put(line)

            code = job(cb)
            self.log_queue.put(f"=== завершено, код {code} ===")
            self.root.after(0, lambda: self._job_done(code, target, total, panel))

        threading.Thread(target=_worker, daemon=True).start()

    def _job_done(self, code: int, target, total: int = 0, panel=None) -> None:
        self.busy = False
        ok = code == 0
        target.config(text="Готово" if ok else f"Завершилось с кодом {code}")
        panel = panel or getattr(self, "task_panel", None)
        if panel is not None:
            # закрываем шаги, которые остались невыполненными
            for i, st in enumerate(panel._steps):
                if st["status"] == "todo":
                    panel.step(i, "fail" if not ok else "done")
            panel.finish(ok, f"{total} фраз" if total else "")
        self._refresh_phrases()
'''


def main() -> None:
    with io.open(GUI, encoding="utf-8") as fh:
        src = fh.read()
    if OLD_RUN not in src:
        print("Блок _run_job не найден")
        return
    src = src.replace(OLD_RUN, NEW_RUN, 1)
    with io.open(GUI, "w", encoding="utf-8") as fh:
        fh.write(src)
    print("Запуск задач переведён на панель шагов")


if __name__ == "__main__":
    main()
