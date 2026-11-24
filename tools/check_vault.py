"""Проверка целостности стека памяти Auraloom в Obsidian.

    python tools\\check_vault.py
"""

from __future__ import annotations

import io
import os
import re

VAULT = r"C:\Users\cyril\Documents\Obsidian\HermesVault\HermesVault"
STACK = os.path.join(VAULT, "80-Память", "10-Проекты", "RedZ-Voice-Studio")
INDEX = os.path.join(VAULT, "80-Память", "00-Индекс.md")

EXPECTED = ["README.md", "00-СОСТОЯНИЕ.md", "01-АРХИТЕКТУРА.md", "02-РЕШЕНИЯ.md",
            "03-ПОДВОДНЫЕ-КАМНИ.md", "04-МЕТРИКИ.md", "05-ИНСТРУМЕНТЫ.md",
            "06-РАБОЧИЙ-КОНТЕКСТ.md"]


def main() -> None:
    if not os.path.isdir(STACK):
        print("СТЕК НЕ НАЙДЕН:", STACK)
        raise SystemExit(1)

    print("=== стек памяти ===")
    missing = []
    for name in EXPECTED:
        path = os.path.join(STACK, name)
        if os.path.exists(path):
            size = os.path.getsize(path)
            head = io.open(path, encoding="utf-8").read(400)
            fm_ok = head.startswith("---") and "type:" in head
            print(f"  {name:<24} {size:>6} байт  frontmatter={'ок' if fm_ok else 'НЕТ'}")
        else:
            missing.append(name)
            print(f"  {name:<24} ОТСУТСТВУЕТ")

    extra = [f for f in os.listdir(STACK) if f not in EXPECTED]
    if extra:
        print("  лишние:", extra)

    print("\n=== ссылки между заметками ===")
    names = {os.path.splitext(f)[0] for f in EXPECTED}
    for name in EXPECTED:
        path = os.path.join(STACK, name)
        if not os.path.exists(path):
            continue
        text = io.open(path, encoding="utf-8").read()
        links = re.findall(r"\[\[([^\]|]+)", text)
        local = [l for l in links if os.path.splitext(os.path.basename(l))[0] in names]
        broken = [l for l in links
                  if l.startswith(("10-Проекты/", "30-Знания/", "40-Рабочий"))
                  and os.path.splitext(os.path.basename(l))[0] not in names
                  and "README" not in l and "MEMORY_PROTOCOL" not in l]
        print(f"  {name:<24} ссылок: {len(links):>2} (внутри стека: {len(local)})"
              + (f"  битых: {broken}" if broken else ""))

    print("\n=== индекс памяти ===")
    idx = io.open(INDEX, encoding="utf-8").read()
    print("  Auraloom в 00-Индекс:", "да" if "RedZ-Voice-Studio" in idx else "НЕТ")

    if missing:
        raise SystemExit(1)
    print("\nСтек полный.")


if __name__ == "__main__":
    main()
