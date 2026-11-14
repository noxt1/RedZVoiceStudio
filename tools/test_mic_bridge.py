"""Тест микрофонного моста: сигнал должен пройти микрофон -> выход.

    python tools\\test_mic_bridge.py

Мост поднимается на реальных устройствах (микрофон + устройство, которое
захватывает Stereo Mix), в микшер подмешивается фраза, и мы проверяем,
что на выходе есть сигнал.
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
    mix_idx, mix_name = hk.find_stereo_mix(inputs)
    render_idx, render_name = hk.find_render_for_capture(inputs, outputs)
    mic_idx, mic_name = core.pick_input_device()

    print(f"Stereo Mix      : {mix_idx} | {mix_name}")
    print(f"устройство вывода: {render_idx} | {render_name}")
    print(f"микрофон        : {mic_idx} | {mic_name}")

    if mix_idx is None or render_idx is None:
        sys.exit("Нет Stereo Mix или пары устройств")

    bridge = mic_bridge.MicBridge(mic_device=mic_idx, render_device=render_idx)
    bridge.start()
    print("\nмост запущен, идёт 3 секунды (поговори, чтобы проверить речь)...")
    time.sleep(3.0)
    st = bridge.status()
    print(f"  микрофон: {st['mic_peak']:.4f} | на выходе: {st['out_peak']:.4f}")

    # подмешиваем фразу
    phrase = os.path.join(sp.output_paths()["out_mp3"], "mx_01.mp3")
    if os.path.exists(phrase):
        ok = bridge.play_phrase(phrase)
        print(f"  фраза подмешана: {ok}")
        time.sleep(2.5)
        st = bridge.status()
        print(f"  после фразы -> на выходе: {st['out_peak']:.4f}")

    bridge.stop()
    print("\nмост остановлен")
    if st["out_peak"] > 0.005:
        print("ИТОГ: сигнал проходит через мост — маршрут рабочий.")
    else:
        print("ИТОГ: на выходе тишина — проверь микрофон/устройство вывода.")


if __name__ == "__main__":
    main()
