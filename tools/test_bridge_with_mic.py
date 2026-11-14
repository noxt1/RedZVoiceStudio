"""Проверка моста с конкретным микрофоном (по умолчанию — запомненный).

    python tools\\test_bridge_with_mic.py
"""

from __future__ import annotations

import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

import hotkeys as hk  # noqa: E402
import mic_bridge  # noqa: E402
import studio_core as core  # noqa: E402
import studio_paths as sp  # noqa: E402


def main() -> None:
    inputs, outputs = hk.list_devices()
    mix_i, mix_n = hk.find_stereo_mix(inputs)
    render_i, render_n = hk.find_render_for_capture(inputs, outputs)

    mic_i, mic_n = core.recalled_mic()
    if mic_i is None:
        mic_i, mic_n = core.pick_input_device()

    print(f"Stereo Mix (микрофон игры): {mix_i} | {mix_n}")
    print(f"устройство вывода          : {render_i} | {render_n}")
    print(f"микрофон (речь)            : {mic_i} | {mic_n}")

    bridge = mic_bridge.MicBridge(mic_device=mic_i, render_device=render_i)
    print(f"подобранная частота моста  : {bridge.sr} Гц")
    try:
        bridge.start()
    except Exception as exc:  # noqa: BLE001
        print("НЕ ЗАПУСТИЛСЯ:", exc)
        raise SystemExit(1)
    print("\nмост работает, 4 секунды (поговори, чтобы проверить речь)...")
    time.sleep(4.0)
    st = bridge.status()
    print(f"  речь с микрофона: {st['mic_peak']:.4f}")
    print(f"  на выходе       : {st['out_peak']:.4f}")

    phrase = os.path.join(sp.output_paths()["out_mp3"], "mx_01.mp3")
    if os.path.exists(phrase):
        bridge.play_phrase(phrase)
        time.sleep(2.5)
        st2 = bridge.status()
        print(f"  после фразы    : {st2['out_peak']:.4f}")
    bridge.stop()
    ok = st2["out_peak"] > 0.01 if "st2" in dir() else st["out_peak"] > 0.01
    print("\nИТОГ:", "маршрут рабочий" if ok else "на выходе тишина")


if __name__ == "__main__":
    main()
