"""Диагностика акустики: слышит ли микрофон динамики.

Играем громкий тон в разные выходы и одновременно пишем с микрофона.

    python tools\\diag_acoustic.py
"""

from __future__ import annotations

import os
import sys
import threading
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

import studio_core as core  # noqa: E402

SR = 48000


def pick_mic():
    mic_i, mic_n = core.recalled_mic()
    if mic_i is None:
        mic_i, mic_n = core.pick_input_device()
    return mic_i, mic_n


def measure(mic_i, out_i, tone, seconds=1.5):
    import sounddevice as sd
    got = []

    def rec():
        try:
            with sd.InputStream(samplerate=SR, channels=1, dtype="float32",
                                device=mic_i, blocksize=1024) as st:
                data, _ = st.read(int(SR * seconds))
                got.append(data[:, 0].copy())
        except Exception as exc:
            print("   запись:", exc)

    th = threading.Thread(target=rec, daemon=True)
    th.start()
    time.sleep(0.3)
    try:
        sd.play(tone, samplerate=SR, device=out_i)
    except Exception as exc:
        print("   вывод:", exc)
    th.join(timeout=seconds + 1)
    if not got:
        return None
    a = got[0]
    return float(np.abs(a).max()), float(np.sqrt((a.astype("float64") ** 2).mean()))


def main() -> None:
    import sounddevice as sd
    mic_i, mic_n = pick_mic()
    print(f"микрофон: {mic_i} | {mic_n}\n")

    # 1. шумовой пол микрофона (тишина 1.5 с)
    peak, rms = measure(mic_i, None, np.zeros(int(SR * 1.5), dtype="float32"))
    print(f"1. шумовой пол микрофона: пик {peak}, rms {rms}\n")

    # 2. громкий тон в разные выходы
    tone = (0.9 * np.sin(2 * np.pi * 1000 * np.arange(int(SR * 1.2)) / SR)).astype("float32")
    devices = sd.query_devices()
    outs = [(i, d["name"]) for i, d in enumerate(devices) if d["max_output_channels"] > 0]
    seen = set()
    for i, name in outs:
        key = name.split("(")[0].strip()
        if key in seen:
            continue
        seen.add(key)
        res = measure(mic_i, i, tone)
        if res:
            print(f"2. {name[:44]:<46} пик {res[0]:.4f} rms {res[1]:.5f}")
        else:
            print(f"2. {name[:44]:<46} нет записи")

    print("\nВывод: если пик ~0 во всех строках — динамики микрофону не слышны "
          "(наушники/гарнитура или слишком тихо).")


if __name__ == "__main__":
    main()
