"""Патч: панель задачи (шаги + прогресс + журнал) вместо простого журнала.

    python tools\\patch_task_panel.py
"""

from __future__ import annotations

import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUI = os.path.join(ROOT, "app", "voice_studio.py")

# 1. импорт панели
OLD_IMPORT = "import hotkeys as hk\nimport mic_bridge\n"
NEW_IMPORT = "import hotkeys as hk\nimport logpanel\nimport mic_bridge\n"

# 2. вкладка «Фразы»: вместо сырого журнала — панель задачи
OLD_PHRASE_LOG = '''        log_box = tk.LabelFrame(self.tab_phrases, text=" Журнал ", bg=BG, fg=DIM,
                                font=("Segoe UI", 9), padx=8, pady=6)
        log_box.pack(fill="both", expand=True, padx=16, pady=(4, 12))
        self.log_text = tk.Text(log_box, bg="#1e2229", fg="#c8cedb", relief="flat",
                                font=("Consolas", 9), height=8)
        self.log_text.pack(fill="both", expand=True)
        self._refresh_phrases()
'''
NEW_PHRASE_LOG = '''        self.task_panel = logpanel.LogPanel(self.tab_phrases, height_steps=6, height_log=9)
        self.task_panel.pack(fill="both", expand=True, padx=16, pady=(4, 12))
        self._refresh_phrases()
'''

# 3. вкладка «Проверка»
OLD_CHECK_LOG = '''        log = tk.LabelFrame(self.tab_check, text=" Отчёт ", bg=BG, fg=DIM,
                            font=("Segoe UI", 9), padx=8, pady=6)
        log.pack(fill="both", expand=True, padx=16, pady=(4, 12))
        self.check_log = tk.Text(log, bg="#1e2229", fg="#c8cedb", relief="flat",
                                font=("Consolas", 9))
        self.check_log.pack(fill="both", expand=True)
'''
NEW_CHECK_LOG = '''        self.check_panel = logpanel.LogPanel(self.tab_check, height_steps=4, height_log=14)
        self.check_panel.pack(fill="both", expand=True, padx=16, pady=(4, 12))
'''

# 4. разбор строки движка -> событие
OLD_DRAIN = '''    def _drain_log(self) -> None:
        """Разбор вывода движка: считаем готовые фразы и показываем журнал."""
        done = 0
        while True:
            try:
                line = self.log_queue.get_nowait()
            except queue.Empty:
                break
            if not line:
                continue
            if line.startswith("["):
                done += 1
                self.progress_lbl.config(text=f"озвучено {done} / {self._job_total}")
            if line.startswith("OK") or "Разборчиво" in line or "синхронно" in line:
                self._log_insert(line, GOOD)
            elif line.startswith("BAD") or "НАЙДЕНЫ" in line:
                self._log_insert(line, WARN)
            else:
                self._log_insert(line)
        self.root.after(150, self._drain_log)

    def _log_insert(self, line: str, color: str | None = None) -> None:
        if not hasattr(self, "log_text"):
            return
        self.log_text.insert("end", line + "\\n", color or "")
        self.log_text.see("end")
'''

NEW_DRAIN = '''    def _drain_log(self) -> None:
        """Разбор вывода движка: шаги, прогресс и журнал."""
        while True:
            try:
                line = self.log_queue.get_nowait()
            except queue.Empty:
                break
            if not line:
                continue
            self._handle_line(line)
        self.root.after(120, self._drain_log)

    def _handle_line(self, line: str) -> None:
        """Одна строка вывода движка -> обновление панели задачи."""
        panel = self._active_panel()
        if panel is None:
            return

        # прогресс генерации: «OK [07] 1.00 12.3s 1.87s Pinche cabron! | Pinche cabrón»
        m = re.match(r"^(OK|BAD|~)\\s*\\[(\\d+)\\]\\s*([\\d.]+)\\s+([\\d.]+)s\\s+(.*?)(?:\\s*\\|\\s*(.*))?$", line)
        if m:
            kind, lid, score, dur, text, heard = m.groups()
            done = int(lid)
            self._job_done_count = done
            panel.progress_set(done)
            panel.step(1, "done" if kind == "OK" else "fail",
                        f"{lid}: {text.strip()[:38]}")
            panel.log("ok" if kind == "OK" else "bad", line)
            return

        if line.startswith("Модель загружена") or "Фраз из приложения" in line:
            panel.log("head", line)
            return
        if "Разборчиво" in line or "синхронно" in line or "Средняя схожесть" in line:
            panel.log("ok", line)
            return
        if "НАЙДЕНЫ" in line or line.startswith("BAD"):
            panel.log("bad", line)
            return
        if line.startswith("==="):
            panel.log("dim", line)
            return
        panel.log("", line)

    def _active_panel(self):
        panel = getattr(self, "_current_panel", None)
        return panel
'''


def main() -> None:
    with io.open(GUI, encoding="utf-8") as fh:
        src = fh.read()
    applied = []
    for label, old, new in (("импорт", OLD_IMPORT, NEW_IMPORT),
                            ("журнал фраз", OLD_PHRASE_LOG, NEW_PHRASE_LOG),
                            ("журнал проверки", OLD_CHECK_LOG, NEW_CHECK_LOG),
                            ("разбор вывода", OLD_DRAIN, NEW_DRAIN)):
        if old in src:
            src = src.replace(old, new, 1)
            applied.append(label)
        else:
            print(f"  ! не найдено: {label}")
    if "import re\n" not in src:
        src = src.replace("import os\n", "import os\nimport re\n", 1)
    with io.open(GUI, "w", encoding="utf-8") as fh:
        fh.write(src)
    print("Применено:", ", ".join(applied) if applied else "ничего")


if __name__ == "__main__":
    main()
