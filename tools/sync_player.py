"""Синхронизировать player/index.html с lines.json.

    python tools\\sync_player.py
"""

from __future__ import annotations

import io
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINES = os.path.join(ROOT, "lines.json")
PLAYER = os.path.join(ROOT, "player", "index.html")


def main() -> None:
    with io.open(LINES, encoding="utf-8") as fh:
        lines = json.load(fh)["lines"]
    with io.open(PLAYER, encoding="utf-8") as fh:
        html = fh.read()

    rows = []
    for l in lines:
        # порядок полей в плеере: id, хоткей, текст (es), перевод (ru), категория
        rows.append('    ["%s","%s","%s","%s","%s"],' % (
            l["id"], l.get("key", ""), l["es"], l.get("ru", ""), l.get("cat", "custom")))

    block = "\n".join(rows)
    new_html, n = re.subn(r"const LINES = \[\n.*?\n\];", "const LINES = [\n" + block + "\n];",
                          html, flags=re.S)
    if n == 0:
        print("блок LINES не найден")
        return
    with io.open(PLAYER, "w", encoding="utf-8") as fh:
        fh.write(new_html)
    print(f"плеер синхронизирован: {len(rows)} фраз")


if __name__ == "__main__":
    main()
