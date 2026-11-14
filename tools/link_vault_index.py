"""Добавить стек RedZ Voice Studio в общий индекс памяти.

    python tools\\link_vault_index.py
"""

from __future__ import annotations

import io
import os

VAULT = r"C:\Users\cyril\Documents\Obsidian\HermesVault\HermesVault"
INDEX = os.path.join(VAULT, "80-Память", "00-Индекс.md")
ANCHOR = "### WildWestGunslinger"

BLOCK = """### RedZ Voice Studio

Стек памяти проекта: [[10-Проекты/RedZ-Voice-Studio/README|RedZ Voice Studio]].

- [[10-Проекты/RedZ-Voice-Studio/00-СОСТОЯНИЕ|Состояние]] — что сделано, где лежит.
- [[10-Проекты/RedZ-Voice-Studio/06-РАБОЧИЙ-КОНТЕКСТ|Рабочий контекст]] — с чего продолжать.
- [[10-Проекты/RedZ-Voice-Studio/03-ПОДВОДНЫЕ-КАМНИ|Подводные камни]] — PortAudio/Mumble/PyInstaller.

"""


def main() -> None:
    text = io.open(INDEX, encoding="utf-8").read()
    if "RedZ-Voice-Studio" in text:
        print("уже добавлено в индекс")
        return
    if ANCHOR not in text:
        print("якорь не найден:", ANCHOR)
        return
    text = text.replace(ANCHOR, BLOCK + ANCHOR, 1)
    io.open(INDEX, "w", encoding="utf-8").write(text)
    print("стек добавлен в 80-Память\\00-Индекс.md")


if __name__ == "__main__":
    main()
