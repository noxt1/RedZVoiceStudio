"""Патч: исключить обобщённые аудиодрайверы из выбора микрофона.

    python tools\\patch_mic_pick.py
"""

from __future__ import annotations

import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "app", "studio_core.py")

OLD = '''    candidates = [(i, d["name"]) for i, d in enumerate(devices) if d["max_input_channels"] > 0]
    if not candidates:
        return None, "нет устройств ввода"
    best, best_score, best_name = None, -1e9, ""
    for idx, name in candidates:
'''

NEW = '''    candidates = [(i, d["name"]) for i, d in enumerate(devices) if d["max_input_channels"] > 0]
    if not candidates:
        return None, "нет устройств ввода"

    # Обобщённые драйверы («Первичный драйвер записи звука», «Стерео микшер»)
    # не являются реальными микрофонами — их лучше не использовать.
    generic = ("первичный драйвер", "primary sound capture", "стерео микшер",
               "stereo mix", "переназначение звуковых устр", "wave out",
               "what u hear")
    real = [(i, n) for i, n in candidates
            if not any(g in n.lower() for g in generic)]
    pool = real or candidates

    best, best_score, best_name = None, -1e9, ""
    for idx, name in pool:
'''


def main() -> None:
    with io.open(TARGET, encoding="utf-8") as fh:
        src = fh.read()
    if OLD not in src:
        print("Фрагмент не найден — правка не нужна")
        return
    src = src.replace(OLD, NEW, 1)
    with io.open(TARGET, "w", encoding="utf-8") as fh:
        fh.write(src)
    print("Выбор микрофона исправлен")


if __name__ == "__main__":
    main()
