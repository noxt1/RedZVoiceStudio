"""Проверка: на какой частоте реально отдаёт данные микрофон.

Открывает InputStream на 44100 и на 48000, считает отсчёты и
спектральный центр. Если на 48000 данные есть, а на 44100 — искажены,
значит best_rate() врёт и запись нужно ресемплить.

    python tools/diag_mic_rate.py
"""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_APP = os.path.join(_ROOT, "app")
if _APP not in sys.path:
    sys.path.insert(0, _APP)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import numpy as np
import sounddevice as sd

import studio_core as core

mic_idx, mic_name = core.recalled_mic()
print("микрофон:", mic_idx, mic_name)
if mic_idx is None:
    dev, mic_name = core.pick_input_device()
    mic_idx = dev
    print("выбран pick_input_device:", mic_idx, mic_name)

print()

for rate in (44100, 48000, 16000, 32000):
    try:
        got = []
        def cb(indata, frames, time_info, status, box=got):
            if status:
                return
            box.append(indata[:, 0].copy())

        with sd.InputStream(device=mic_idx, channels=1, samplerate=rate,
                            dtype="float32", blocksize=1024, callback=cb):
            import time
            time.sleep(1.0)

        if not got:
            print(f"{rate} Гц: нет данных")
            continue

        data = np.concatenate(got)
        peak = float(np.abs(data).max())
        rms = float(np.sqrt((data.astype(np.float64) ** 2).mean()))

        n = min(len(data), 1 << 15)
        if n > 1024:
            seg = data[:n] * np.hanning(n)
            spec = np.abs(np.fft.rfft(seg))
            freqs = np.fft.rfftfreq(n, 1.0 / rate)
            centroid = float((spec * freqs).sum() / (spec.sum() or 1.0))
        else:
            centroid = 0.0

        print(f"{rate} Гц: отсчётов={len(data):>7}  пик={peak:.4f}  "
              f"RMS={rms:.5f}  центр={centroid:.0f} Гц")
    except Exception as exc:
        print(f"{rate} Гц: не открылся — {exc}")

print()
print("Если на 48000 данных больше и RMS выше — микрофон работает на 48к,")
print("а запись в 44100 даёт «писк» из-за неверной метки частоты.")