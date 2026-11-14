"""Патч: убрать дублирующий прогресс-лейбл (панель шагов — единственный статус).

    python tools\\patch_clean_progress.py
"""

from __future__ import annotations

import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUI = os.path.join(ROOT, "app", "voice_studio.py")

OLD = '''        self.phrase_status = self._lbl(self.tab_phrases, "", 10, DIM)
        self.phrase_status.pack(anchor="w", padx=16, pady=(0, 4))
        self.progress_lbl = self._lbl(self.tab_phrases, "", 10, ACCENT)
        self.progress_lbl.pack(anchor="w", padx=16, pady=(0, 4))
'''
NEW = '''        self.phrase_status = self._lbl(self.tab_phrases, "", 10, DIM)
        self.phrase_status.pack(anchor="w", padx=16, pady=(0, 4))
        # прогресс показывает панель шагов (app/logpanel.py)
        self.progress_lbl = None
'''

OLD2 = '''        self.progress_lbl = self._lbl(self.tab_voice, "", 10, DIM)'''
if OLD2 in (""):
    pass


def main() -> None:
    with io.open(GUI, encoding="utf-8") as fh:
        src = fh.read()
    if OLD not in src:
        print("фрагмент не найден")
        return
    src = src.replace(OLD, NEW, 1)
    # на вкладке «Голос» свой лейбл прогресса больше не нужен
    src = src.replace('        self.progress_lbl = self._lbl(self.tab_voice, "", 10, DIM)\n'
                      '        self.progress_lbl.pack(anchor="w", padx=16, pady=(0, 2))\n', "")
    with io.open(GUI, "w", encoding="utf-8") as fh:
        fh.write(src)
    print("Дублирующий прогресс-лейбл убран")


if __name__ == "__main__":
    main()
