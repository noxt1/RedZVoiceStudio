"""Патч: надёжный запуск задач — сброс busy, этапы, «отменить», таймер.

Что чиним:
  1. Исключение в рабочем потоке оставляло self.busy = True навсегда ->
     все кнопки начинали писать «Занято» и ничего не делали.
  2. Пока модель грузится (~30 с) и идёт генерация, не было видно этапа ->
     появится heartbeat с прошедшим временем и явные переходы по шагам.
  3. Долгую генерацию нельзя было прервать -> кнопка «Отменить».

    python tools\\patch_job_robust.py
"""

from __future__ import annotations

import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUI = os.path.join(ROOT, "app", "voice_studio.py")
CORE = os.path.join(ROOT, "app", "studio_core.py")


def patch_core() -> None:
    with io.open(CORE, encoding="utf-8") as fh:
        src = fh.read()

    old = '''def run_engine(args: list[str], on_line=None, cwd: str | None = None) -> int:
    """Запустить скрипт движком, транслируя вывод в колбэк."""
    python = sp.engine_python()
    if not python:
        return -1
    proc = subprocess.Popen(
        [python, *args], cwd=cwd or sp.workspace(),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
    )
    for line in proc.stdout:
        if on_line:
            on_line(line.rstrip())
    return proc.wait()
'''

    new = '''_active_proc = None


def cancel_job() -> bool:
    """Прервать текущую задачу движка."""
    global _active_proc
    if _active_proc is None:
        return False
    try:
        _active_proc.kill()
        return True
    except Exception:
        return False


def run_engine(args: list[str], on_line=None, cwd: str | None = None) -> int:
    """Запустить скрипт движком, транслируя вывод в колбэк."""
    global _active_proc
    python = sp.engine_python()
    if not python:
        return -1
    proc = subprocess.Popen(
        [python, *args], cwd=cwd or sp.workspace(),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
    )
    _active_proc = proc
    try:
        for line in proc.stdout:
            if on_line:
                on_line(line.rstrip())
    finally:
        _active_proc = None
    return proc.wait()
'''
    if old not in src:
        print("core: run_engine не найден")
    else:
        src = src.replace(old, new, 1)
        with io.open(CORE, "w", encoding="utf-8") as fh:
            fh.write(src)
        print("core: добавлена отмена задачи")


def patch_gui() -> None:
    with io.open(GUI, encoding="utf-8") as fh:
        src = fh.read()

    # 1) worker: всегда сбрасывать busy и показывать ошибку
    old_worker = '''        def _worker():
            def cb(line: str) -> None:
                self.log_queue.put(line)

            code = job(cb)
            self.log_queue.put(f"=== завершено, код {code} ===")
            self.root.after(0, lambda: self._job_done(code, target, total, panel))

        threading.Thread(target=_worker, daemon=True).start()
'''
    new_worker = '''        def _worker():
            def cb(line: str) -> None:
                self.log_queue.put(line)

            code, error = -1, ""
            try:
                code = job(cb)
            except Exception as exc:  # noqa: BLE001
                error = f"{type(exc).__name__}: {exc}"
                self.log_queue.put(f"ОШИБКА ЗАДАЧИ: {error}")
            finally:
                # busy сбрасываем ВСЕГДА, иначе кнопки навсегда «Занято»
                self.log_queue.put(f"=== завершено, код {code} ===")
                self.root.after(0, lambda: self._job_done(code, target, total, panel, error))

        threading.Thread(target=_worker, daemon=True).start()
        self._heartbeat()
'''
    # 2) _job_done с ошибкой
    old_done = '''    def _job_done(self, code: int, target, total: int = 0, panel=None) -> None:
        self.busy = False
        ok = code == 0
        target.config(text="Готово" if ok else f"Завершилось с кодом {code}")
'''
    new_done = '''    def _job_done(self, code: int, target, total: int = 0, panel=None,
                  error: str = "") -> None:
        self.busy = False
        ok = code == 0 and not error
        if error:
            target.config(text=f"Ошибка: {error[:80]}")
        else:
            target.config(text="Готово" if ok else f"Завершилось с кодом {code}")
'''
    # 3) heartbeat + отмена
    old_after = '''        self.root.after(120, self._drain_log)
'''
    new_after = '''        self.root.after(120, self._drain_log)

    def _heartbeat(self) -> None:
        """Пока задача идёт — показываем, что процесс жив и сколько прошло."""
        if self.busy:
            panel = getattr(self, "_current_panel", None)
            if panel is not None:
                panel.heartbeat()
        self.root.after(1000, self._heartbeat)

    def _cancel_job(self) -> None:
        import studio_core as core
        if not self.busy:
            self.phrase_status.config(text="Нечего отменять")
            return
        ok = core.cancel_job()
        self.phrase_status.config(text="Задача отменена" if ok else "Нечего отменять")
'''
    applied = []
    for label, old, new in (("worker", old_worker, new_worker),
                           ("job_done", old_done, new_done),
                           ("heartbeat", old_after, new_after)):
        if old in src:
            src = src.replace(old, new, 1)
            applied.append(label)
        else:
            print(f"  ! не найдено: {label}")

    # 4) кнопка «Отменить» рядом с «Озвучить всё»
    old_btn = '''        self._btn(btns, "★ Озвучить всё моим голосом", self._voice_all, "#1e6f3f", "#fff", 10, 14, 8).pack(side="left")
'''
    new_btn = '''        self._btn(btns, "★ Озвучить всё моим голосом", self._voice_all, "#1e6f3f", "#fff", 10, 14, 8).pack(side="left", padx=(0, 8))
        self._btn(btns, "■ Отменить", self._cancel_job, "#7a2f2f", "#fff", 10, 12, 8).pack(side="left")
'''
    if old_btn in src:
        src = src.replace(old_btn, new_btn, 1)
        applied.append("кнопка отмены")
    else:
        print("  ! не найдено: кнопка отмены")

    with io.open(GUI, "w", encoding="utf-8") as fh:
        fh.write(src)
    print("gui: применено:", ", ".join(applied))


if __name__ == "__main__":
    patch_core()
    patch_gui()
