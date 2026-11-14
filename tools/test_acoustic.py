"""Тест акустического режима: фраза в динамики -> микрофон её слышит.

    python tools\\test_acoustic.py
"""

from __future__ import annotations

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

import acoustic  # noqa: E402
import hotkeys as hk  # noqa: E402
import studio_core as core  # noqa: E402
import studio_paths as sp  # noqa: E402


def main() -> None:
    import sounddevice as sd

    ws = sp.workspace()
    phrase = os.path.join(ws, "out", "mp3", "mx_01.mp3")
    if not os.path.exists(phrase):
        sys.exit("Нет озвучки")

    mic_i, mic_n = core.recalled_mic()
    if mic_i is None:
        mic_i, mic_n = core.pick_input_device()
    print(f"микрофон: {mic_i} | {mic_n}")

    # выход: динамики (не наушники!) — чтобы микрофон услышал
    devices = sd.query_devices()
    spk = [(i, d["name"]) for i, d in enumerate(devices)
           if d["max_output_channels"] > 0
           and any(k in d["name"].lower() for k in ("динамики", "speakers", "lg ultragear"))]
    print("динамики:", spk)

    for out_i, out_n in spk:
        player = acoustic.AcousticPlayer(out_device=out_i, mic_device=mic_i)
        res = player.calibrate(phrase)
        if res.get("ok"):
            print(f"  {out_n[:40]:<42} gain={res['gain']:.2f} "
                  f"уровень в микрофоне={res['level']:.3f} {res.get('reason','')}")
        else:
            print(f"  {out_n[:40]:<42} не сработало: {res.get('reason')}")


if __name__ == "__main__":
    main()
