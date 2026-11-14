"""Проверка: какие символы испанского не кодируются в cp1251.

    python tools\\check_encoding.py
"""

from __future__ import annotations

import sys


def main() -> None:
    chars = ["\u00e9", "\u00f3", "\u00e1", "\u00ed", "\u00fa", "\u00f1",
             "\u00a1", "\u00fc", "\u00a8", "\u00e8"]
    names = {"\u00e9": "e-acute", "\u00f3": "o-acute", "\u00e1": "a-acute",
             "\u00ed": "i-acute", "\u00fa": "u-acute", "\u00f1": "n-tilde",
             "\u00a1": "i-exclam", "\u00fc": "u-diaeresis",
             "\u00a8": "dieresis", "\u00e8": "e-grave"}
    print(f"stdout encoding в этом процессе: {sys.stdout.encoding}")
    for ch in chars:
        try:
            ch.encode("cp1251")
            ok = "да"
        except Exception:
            ok = "НЕТ"
        print(f"  {names[ch]:<12} U+{ord(ch):04X}  в cp1251: {ok}")

    print("\nПроверка реальной строки движка:")
    line = "OK [03] 1.00   1.22s  Orale, carnal!  | \u00a1Horale, carnal!"
    try:
        line.encode("cp1251")
        print("  строка кодируется в cp1251: да")
    except Exception as exc:
        print(f"  строка НЕ кодируется в cp1251: {exc}")
    try:
        line.encode("utf-8")
        print("  строка кодируется в utf-8: да")
    except Exception as exc:
        print(f"  строка НЕ кодируется в utf-8: {exc}")


if __name__ == "__main__":
    main()
