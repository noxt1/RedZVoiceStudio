"""Патч: панель задачи — heartbeat и переходы по этапам.

    python tools\\patch_panel_heartbeat.py
"""

from __future__ import annotations

import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PANEL = os.path.join(ROOT, "app", "logpanel.py")
GUI = os.path.join(ROOT, "app", "voice_studio.py")


def patch_panel() -> None:
    with io.open(PANEL, encoding="utf-8") as fh:
        src = fh.read()

    old = '''    def finish(self, ok: bool, summary: str = "") -> None:'''
    new = '''    def heartbeat(self) -> None:
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

    def finish(self, ok: bool, summary: str = "") -> None:'''
    if old not in src:
        print("panel: finish не найден")
        return
    src = src.replace(old, new, 1)
    with io.open(PANEL, "w", encoding="utf-8") as fh:
        fh.write(src)
    print("panel: добавлены heartbeat и set_stage")


def patch_gui() -> None:
    with io.open(GUI, encoding="utf-8") as fh:
        src = fh.read()

    # этапы по строкам вывода движка
    old = '''        if line.startswith("Модель загружена") or "Фраз из приложения" in line:
            panel.log("head", line)
            return
'''
    new = '''        if "Фраз из приложения" in line:
            panel.log("head", line)
            panel.step(0, "done", line.split(":")[-1].strip() + " фраз")
            panel.set_stage(1, "передача в движок")
            return
        if line.startswith("Модель загружена"):
            panel.log("head", line)
            panel.set_stage(1, "модель загружена")
            return
        if line.startswith("Проверка качества"):
            panel.log("dim", line)
            return
'''
    if old not in src:
        print("gui: блок этапов не найден")
        return
    src = src.replace(old, new, 1)

    # прогресс по фразам -> двигаем шаг генерации
    old2 = '''            panel.step(1, "done" if kind == "OK" else "fail",
                        f"{lid}: {text.strip()[:38]}")
            panel.log("ok" if kind == "OK" else "bad", line)
            return
'''
    new2 = '''            panel.set_stage(1, f"{lid}: {text.strip()[:34]}")
            panel.step(2, "doing", "разборчивость проверяется по факту")
            panel.log("ok" if kind == "OK" else "bad", line)
            return
'''
    if old2 not in src:
        print("gui: блок прогресса не найден")
    else:
        src = src.replace(old2, new2, 1)

    with io.open(GUI, "w", encoding="utf-8") as fh:
        fh.write(src)
    print("gui: переходы по этапам добавлены")


if __name__ == "__main__":
    patch_panel()
    patch_gui()
