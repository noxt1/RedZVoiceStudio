"""Перегенерировать keybinds.lua и player/index.html из lines.json.

    python tools\\sync_assets.py
"""

from __future__ import annotations

import io
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINES = os.path.join(ROOT, "lines.json")
KEYBINDS = os.path.join(ROOT, "keybinds.lua")
PLAYER = os.path.join(ROOT, "player", "index.html")

KEY_TEMPLATE = "-- Горячие клавиши звуковой панели Auraloom.\n" \
               "-- Клавиши можно переназначить в настройках FiveM (Settings -> Key Bindings):\n" \
               "--   sbplay1 ... sbplay{count}\n\n" \
               "local binds = {{\n" \
               "{rows}" \
               "}}\n\n" \
               "for i, b in ipairs(binds) do\n" \
               "    RegisterKeyMapping(b.cmd, string.format('SB %02d - %s', i, b.desc), 'keyboard', b.key)\n" \
               "end\n"


def main() -> None:
    with io.open(LINES, encoding="utf-8") as fh:
        lines = json.load(fh)["lines"]

    # --- keybinds.lua ---
    rows = []
    for l in lines:
        key = (l.get("key") or "").strip()
        if not key:
            continue
        desc = l["es"].replace("'", "")
        rows.append("    {cmd = 'sbplay%s', key = '%s', desc = '%s'},"
                    % (l["id"], key, desc))
    with io.open(KEYBINDS, "w", encoding="utf-8") as fh:
        fh.write(KEY_TEMPLATE.format(count=len(lines), rows="\n".join(rows) + "\n"))
    print(f"keybinds.lua: {len(rows)} биндов")

    # --- player/index.html ---
    with io.open(PLAYER, encoding="utf-8") as fh:
        html = fh.read()
    prows = []
    for l in lines:
        prows.append('    ["%s","%s","%s","%s","%s"],' % (
            l["id"], l.get("key", ""), l["es"], l.get("ru", ""), l.get("cat", "custom")))
    block = "\n".join(prows)
    new_html, n = re.subn(r"const LINES = \[\n.*?\n\];",
                          "const LINES = [\n" + block + "\n];", html, flags=re.S)
    if n:
        with io.open(PLAYER, "w", encoding="utf-8") as fh:
            fh.write(new_html)
    print(f"player/index.html: {len(prows)} фраз")


if __name__ == "__main__":
    main()
