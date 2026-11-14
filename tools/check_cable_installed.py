"""Проверить, появились ли устройства виртуального кабеля в системе.

    "<engine>\\Scripts\\python.exe" tools\\check_cable_installed.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))

import cable  # noqa: E402


def main() -> None:
    import sounddevice as sd

    print("=== устройства с «cable» в названии ===")
    found = False
    for i, d in enumerate(sd.query_devices()):
        if "cable" in d["name"].lower():
            found = True
            print(f"  [{i}] {d['name']:<40} вход={d['max_input_channels']} "
                  f"выход={d['max_output_channels']} sr={int(d['default_samplerate'])}")
    if not found:
        print("  нет — кабель не установлен")

    print("\n=== через модуль cable ===")
    devs = cable.cable_devices()
    print("  найдено:", devs if devs else "нет")
    print("  установлен:", cable.is_installed())

    print("\n=== установщик на диске ===")
    setup = cable.setup_path()
    print("  путь:", setup if setup else "нет")
    if setup:
        print("  размер:", os.path.getsize(setup), "байт")


if __name__ == "__main__":
    main()
