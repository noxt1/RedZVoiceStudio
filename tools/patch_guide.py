"""Замена блока guide_text в voice_studio.py.

Строки собираются через NL = chr(92) + 'n', чтобы шелл не съел экранирование.

    python tools\\patch_guide.py
"""

from __future__ import annotations

import io
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "app", "voice_studio.py")

NL = chr(92) + "n"
LINES = [
    "Если мост не подходит, есть ещё варианты:",
    "  • Ресурс на сервере (вкладка «В игру») — фразу играет сервер,",
    "    микрофон вообще не затрагивается, ничего ставить не надо.",
    "  • Stereo Mix без моста: играем в устройство, которое он захватывает;",
    "    свою речь туда же — mmsys.cpl -> Запись -> микрофон -> Свойства ->",
    "    «Прослушивать это устройство» -> вывод Realtek USB Audio.",
    "  • VoiceMeeter/VB-CABLE — если реплики должны идти именно голосом,",
    "    а микрофон остался чистым.",
]


def build() -> str:
    out = ["        guide_text = ("]
    for line in LINES:
        out.append(f'            "{line}{NL}"')
    out.append("        )")
    return "\n".join(out) + "\n"


def main() -> None:
    with io.open(TARGET, encoding="utf-8") as fh:
        src = fh.read()

    pattern = re.compile(r"        guide_text = \(\n(?:.*\n)*?        \)\n")
    new_src, n = pattern.subn(lambda m: build(), src, count=1)
    if n == 0:
        print("Блок guide_text не найден — правка не нужна")
        return
    with io.open(TARGET, "w", encoding="utf-8") as fh:
        fh.write(new_src)
    print("Блок guide_text заменён")


if __name__ == "__main__":
    main()
