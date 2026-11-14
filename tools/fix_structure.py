"""Починить lines.json (структура) и check_sync.py (регекс плеера).

    python tools\\fix_structure.py
"""

from __future__ import annotations

import io
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINES = os.path.join(ROOT, "lines.json")
CHECK = os.path.join(ROOT, "tools", "check_sync.py")


def fix_lines() -> None:
    with io.open(LINES, encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, list):
        data = {"lines": data}
    # добираем недостающие ключи
    for i, l in enumerate(data["lines"]):
        l.setdefault("id", f"{i + 1:02d}")
        l.setdefault("key", "")
        l.setdefault("cat", "custom")
        l.setdefault("es", "")
        l.setdefault("ru", "")
        l.setdefault("vo", "M")
    with io.open(LINES, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    print("lines.json: структура восстановлена, фраз:", len(data["lines"]))


def fix_check() -> None:
    with io.open(CHECK, encoding="utf-8") as fh:
        src = fh.read()
    # ровная регекс: id, key, text, ru, cat (key и ru могут быть пустыми)
    pattern = r'pl = re\.findall\(r?"\[\(\d\+\).*?", html\)'
    replacement = ('pl = re.findall(r\'\\["(\\d+)","([^"]*)","([^"]+)","([^"]*)","([^"]+)"\]\', html)')
    new_src, n = re.subn(pattern, replacement, src)
    if n:
        with io.open(CHECK, "w", encoding="utf-8") as fh:
            fh.write(new_src)
        print("check_sync.py: регекс исправлен")
    else:
        print("check_sync.py: регекс не найден (проверь вручную)")


if __name__ == "__main__":
    fix_lines()
    fix_check()
