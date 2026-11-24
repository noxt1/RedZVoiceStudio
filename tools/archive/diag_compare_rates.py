"""СРАВНЕНИЕ записи на 44100 и 48000 — какая даёт нормальный звук.

Записывает по 2 секунды на каждой частоте в отдельные файлы,
считает RMS и спектральный центр.

    python tools/diag_compare_rates.py
"""

from __future__ import annotations

import os
import sys
import time

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
import soundfile as sf

import studio_core as core
import studio_paths as sp

out_dir = sp.output_paths()["samples"]
os.makedirs(out_dir, exist_ok=True)

dev_idx, dev_name = core.recalled_mic()
print("устройство:", dev_idx, dev_name)
print()

for rate in (44100, 48000):
    got = []

    def cb(indata, frames, time_info, status, box=got):
        if status:
            return
        box.append(indata[:, 0].copy())

    try:
        t0 = time.time()
        with sd.InputStream(device=dev_idx, channels=1, samplerate=rate,
                            dtype="float32", blocksize=1024, callback=cb):
            time.sleep(2.0)
        wall = time.time() - t0

        if not got:
            print(f"{rate} Гц: нет данных")
            continue

        data = np.concatenate(got)
        peak = float(np.abs(data).max())
        rms = float(np.sqrt((data.astype(np.float64) ** 2).mean()))

        n = min(len(data), 1 << 15)
        seg = data[:n] * np.hanning(n)
        spec = np.abs(np.fft.rfft(seg))
        freqs = np.fft.rfftfreq(n, 1.0 / rate)
        centroid = float((spec * freqs).sum() / (spec.sum() or 1.0))

        path = os.path.join(out_dir, f"_diag_{rate}.wav")
        sf.write(path, data, rate, subtype="PCM_16")

        print(f"{rate} Гц: отсчётов={len(data):>7}  {len(data)/rate:.2f} c  "
              f"пик={peak:.5f}  RMS={rms:.6f}  центр={centroid:.0f} Гц")
        print(f"   -> {path}")
    except Exception as exc:
        print(f"{rate} Гц: ошибка — {exc}")

    time.sleep(0.5)

print()
print("Нормальная речь: RMS 0.005–0.15, спектральный центр 300–1800 Гц.")
print("Если у 44100 RMS крошечный, а центр высокий — запись битая.")