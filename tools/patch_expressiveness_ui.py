"""Патч: слайдер «Живость интонации» на вкладке «Фразы».

    python tools\\patch_expressiveness_ui.py
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

    old = '''def clone_all(reference: str, attempts: int = 10, on_line=None, texts=None) -> int:'''
    new = '''def clone_all(reference: str, attempts: int = 10, on_line=None, texts=None,
              expressiveness: int = 2) -> int:'''
    if old in src:
        src = src.replace(old, new, 1)
    else:
        print("core: clone_all не найден")

    old2 = '''    args = [script, "--reference", reference, "--attempts", str(attempts),
            "--out", _out_root()]'''
    new2 = '''    args = [script, "--reference", reference, "--attempts", str(attempts),
            "--expressiveness", str(expressiveness),
            "--out", _out_root()]'''
    if old2 in src:
        src = src.replace(old2, new2, 1)
    else:
        print("core: аргументы clone_all не найдены")

    old3 = '''def clone_one(text: str, reference: str, phrase_id: str, on_line=None) -> int:'''
    new3 = '''def clone_one(text: str, reference: str, phrase_id: str, on_line=None,
              expressiveness: int = 2) -> int:'''
    if old3 in src:
        src = src.replace(old3, new3, 1)
    else:
        print("core: clone_one не найден")

    old4 = '''    return run_engine([script, "--reference", reference, "--text", text,
                        "--id", phrase_id, "--out", _out_root()], on_line=on_line)'''
    new4 = '''    return run_engine([script, "--reference", reference, "--text", text,
                        "--id", phrase_id, "--expressiveness", str(expressiveness),
                        "--out", _out_root()], on_line=on_line)'''
    if old4 in src:
        src = src.replace(old4, new4, 1)
    else:
        print("core: вызов clone_one не найден")

    with io.open(CORE, "w", encoding="utf-8") as fh:
        fh.write(src)
    print("core: выразительность прокинута в движок")


def patch_gui() -> None:
    with io.open(GUI, encoding="utf-8") as fh:
        src = fh.read()

    # слайдер рядом с кнопками
    old = '''        self._btn(btns, "■ Отменить", self._cancel_job, "#7a2f2f", "#fff", 10, 12, 8).pack(side="left")
'''
    new = '''        self._btn(btns, "■ Отменить", self._cancel_job, "#7a2f2f", "#fff", 10, 12, 8).pack(side="left")

        # Живость интонации: 0 — ровно, 3 — максимум выразительности
        self._lbl(btns, "Живость:", 10, DIM).pack(side="left", padx=(16, 4))
        self.expr_var = tk.IntVar(value=2)
        expr_scale = ttk.Scale(btns, from_=0, to=3, variable=self.expr_var,
                                orient="horizontal", length=110)
        expr_scale.pack(side="left")
        self.expr_lbl = self._lbl(btns, "2", 10, ACCENT)
        self.expr_lbl.pack(side="left", padx=(4, 0))
        self.expr_var.trace_add("write", lambda *_: self.expr_lbl.config(
            text=str(self.expr_var.get())))
'''
    if old in src:
        src = src.replace(old, new, 1)
    else:
        print("gui: кнопка отмены не найдена")

    # передаём значение в задачи
    old2 = '''            code = core.clone_all(ref, 8, cb, texts=payload)'''
    new2 = '''            code = core.clone_all(ref, 8, cb, texts=payload,
                                  expressiveness=self.expr_var.get())'''
    if old2 in src:
        src = src.replace(old2, new2, 1)
    else:
        print("gui: вызов clone_all не найден")

    old3 = '''            code = core.clone_one(phrase["text"], ref, phrase["id"], cb)'''
    new3 = '''            code = core.clone_one(phrase["text"], ref, phrase["id"], cb,
                                  expressiveness=self.expr_var.get())'''
    if old3 in src:
        src = src.replace(old3, new3, 1)
    else:
        print("gui: вызов clone_one не найден")

    with io.open(GUI, "w", encoding="utf-8") as fh:
        fh.write(src)
    print("gui: слайдер «Живость» добавлен")


if __name__ == "__main__":
    patch_core()
    patch_gui()
