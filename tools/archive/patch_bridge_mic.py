"""Патч: мост использует выбранный пользователем микрофон, а не автоподбор.

Плюс: в списке микрофонов убираем обобщённые драйверы и сам Stereo Mix
(он нужен как микрофон В ИГРЕ, а не как источник речи).

    python tools\\patch_bridge_mic.py
"""

from __future__ import annotations

import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "app", "voice_studio.py")

OLD_LIST = '''        self.out_combo["values"] = [f"{i}: {n}" for i, n in outs]
        self.in_combo["values"] = [f"{i}: {n}" for i, n in inputs]
'''

NEW_LIST = '''        self.out_combo["values"] = [f"{i}: {n}" for i, n in outs]
        # В списке микрофонов только реальные: без обобщённых драйверов и Stereo Mix
        mic_inputs = [(i, n) for i, n in inputs
                      if not hk.is_stereo_mix(n)
                      and not any(g in n.lower() for g in
                                  ("первичный драйвер", "primary sound capture",
                                   "переназначение звуковых устр"))]
        self.in_combo["values"] = [f"{i}: {n}" for i, n in (mic_inputs or inputs)]
'''

OLD_PICK = '''        # микрофон для речи: то, что слушает пользователь
        mic_idx, mic_name = core.pick_input_device()
        if mic_idx is None:
            self.bridge_info.config(text="микрофон не найден")
            return
'''

NEW_PICK = '''        # микрофон для речи: выбранный пользователем (иначе — автоподбор)
        mic_idx = self.in_device
        mic_name = ""
        if mic_idx is not None:
            for i, n in inputs:
                if i == mic_idx:
                    mic_name = n
                    break
        if mic_idx is None:
            mic_idx, mic_name = core.pick_input_device()
        if mic_idx is None:
            self.bridge_info.config(text="микрофон не найден")
            return
'''

OLD_COMBO = '''        if inputs:
            pick_in = next((i for i, n in inputs if i == cur_in), inputs[0][0])
'''

NEW_COMBO = '''        if inputs:
            pool = mic_inputs or inputs
            pick_in = next((i for i, n in pool if i == cur_in), pool[0][0])
'''


def main() -> None:
    with io.open(TARGET, encoding="utf-8") as fh:
        src = fh.read()
    applied = []
    for name, old, new in (("список микрофонов", OLD_LIST, NEW_LIST),
                           ("выбор микрофона мостом", OLD_PICK, NEW_PICK),
                           ("микрофон по умолчанию", OLD_COMBO, NEW_COMBO)):
        if old in src:
            src = src.replace(old, new, 1)
            applied.append(name)
        else:
            print(f"  ! не найдено: {name}")
    with io.open(TARGET, "w", encoding="utf-8") as fh:
        fh.write(src)
    print("Применено:", ", ".join(applied) if applied else "ничего")


if __name__ == "__main__":
    main()
