"""Патч: осмысленные шаги для каждой кнопки.

    python tools\\patch_button_steps.py
"""

from __future__ import annotations

import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUI = os.path.join(ROOT, "app", "voice_studio.py")

REPLACEMENTS = [
    # --- озвучка одной фразы ---
    ('''        self._run_job("Озвучиваю фразу…",
                      lambda cb: core.clone_one(phrase["text"], ref, phrase["id"], cb),
                      status=self.phrase_status, total=1)''',
     '''        self._run_job(
            f"Озвучка фразы: {phrase['text'][:40]}",
            lambda cb: core.clone_one(phrase["text"], ref, phrase["id"], cb),
            status=self.phrase_status, total=1,
            steps=["Проверка образца голоса", "Генерация фразы (XTTS)",
                   "Проверка разборчивости", "Сохранение файла"])'''),

    # --- озвучка всех фраз ---
    ('''        self._run_job("Озвучиваю все фразы…",
                      lambda cb: core.clone_all(ref, 8, cb, texts=payload),
                      status=self.phrase_status, total=len(payload))''',
     '''        self._run_job(
            f"Озвучка {len(payload)} фраз твоим голосом",
            lambda cb: core.clone_all(ref, 8, cb, texts=payload),
            status=self.phrase_status, total=len(payload),
            steps=["Проверка образца голоса", "Передача списка фраз движку",
                   "Генерация фраз (XTTS)", "Проверка разборчивости",
                   "Раскладка в sounds/ и player/mp3/"])'''),

    # --- проверка разборчивости ---
    ('''    def _check_quality(self) -> None:
        self._check_run("Проверяю разборчивость…", core.verify_quality)''',
     '''    def _check_quality(self) -> None:
        self._check_run("Проверка разборчивости", core.verify_quality,
                        steps=["Запуск проверки", "Распознавание реплик (Whisper)",
                               "Проверка фонем", "Отчёт"])'''),

    # --- проверка схожести ---
    ('''        self._check_run("Считаю схожесть голоса…", lambda cb: core.verify_similarity(ref, cb))''',
     '''        self._check_run("Проверка схожести голоса",
                        lambda cb: core.verify_similarity(ref, cb),
                        steps=["Подготовка эталона", "Расчёт эмбеддингов (ECAPA)",
                               "Сравнение с референсом", "Отчёт"])'''),

    # --- проверка правил ---
    ('''    def _check_rules(self) -> None:
        self._check_run("Проверяю правила проекта…", core.verify_rules)''',
     '''    def _check_rules(self) -> None:
        self._check_run("Проверка правил проекта (п.3.2)", core.verify_rules,
                        steps=["Загрузка реплик", "Поиск упоминаний родственников",
                               "Проверка наличия мата", "Отчёт"])'''),

    # --- проверка синхронности ---
    ('''    def _check_sync(self) -> None:
        self._check_run("Проверяю синхронность…", core.verify_sync)''',
     '''    def _check_sync(self) -> None:
        self._check_run("Проверка синхронности файлов", core.verify_sync,
                        steps=["Сверка озвучки с манифестом", "Сверка плеера и биндов",
                               "Отчёт"])'''),

    # --- _check_run: шаги и панель ---
    ('''    def _check_run(self, title: str, job) -> None:
        self.check_status.config(text=title)
        self.check_log.delete("1.0", "end")

        def _worker():
            def cb(line: str) -> None:
                self.check_log.insert("end", line + "\\n")
                self.check_log.see("end")
            job(cb)

        threading.Thread(target=_worker, daemon=True).start()''',
     '''    def _check_run(self, title: str, job, steps: list[str] | None = None) -> None:
        self.check_status.config(text=title)
        panel = getattr(self, "check_panel", None)
        self._current_panel = panel
        if panel is not None:
            panel.begin(title, steps or ["Выполнение"], 0)

        def _worker():
            def cb(line: str) -> None:
                self.log_queue.put(line)
            code = job(cb)
            self.log_queue.put(f"=== завершено, код {code} ===")
            self.root.after(0, lambda: self._check_done(code, panel))

        threading.Thread(target=_worker, daemon=True).start()

    def _check_done(self, code: int, panel=None) -> None:
        panel = panel or getattr(self, "check_panel", None)
        if panel is not None:
            for i, st in enumerate(panel._steps):
                if st["status"] == "todo":
                    panel.step(i, "done" if code == 0 else "fail")
            panel.finish(code == 0)'''),
]


def main() -> None:
    with io.open(GUI, encoding="utf-8") as fh:
        src = fh.read()
    applied = []
    for label, old, new in REPLACEMENTS:
        if old in src:
            src = src.replace(old, new, 1)
            applied.append(label)
        else:
            print(f"  ! не найдено: {label}")
    with io.open(GUI, "w", encoding="utf-8") as fh:
        fh.write(src)
    print("Применено:", ", ".join(applied) if applied else "ничего")


if __name__ == "__main__":
    main()
