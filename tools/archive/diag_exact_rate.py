"""ТОЧНЫЙ замер: сколько отсчётов приходит за секунду.

Ключ к «ускорению»: если поток просит 16000 Гц, а устройство физически
48000, то за 1 секунду придёт 48000 отсчётов (в 3 раза больше).

Меряем по time.perf_counter в колбэке (time_info недоступен).

    python tools/diag_exact_rate.py
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
import studio_core as core

dev_idx, dev_name = core.recalled_mic()
print("устройство:", dev_idx, dev_name)
print()

print(f"{'запрос':>8} {'отсчётов':>10} {'wall, c':>9} {'отс/с':>10} {'вывод'}")
print("-" * 60)

for req in (16000, 44100, 48000):
    got = []
    stamps = []

    def cb(indata, frames, time_info, status, box=got, st=stamps):
        box.append(len(indata))
        st.append(time.perf_counter())

    try:
        with sd.InputStream(device=dev_idx, channels=1, samplerate=req,
                            dtype="float32", blocksize=1024, callback=cb):
            t0 = time.perf_counter()
            while time.perf_counter() - t0 < 2.5:
                time.sleep(0.05)
                if sum(got) >= req:
                    break

        total = sum(got)
        if len(stamps) >= 2:
            wall = stamps[-1] - stamps[0]
        else:
            wall = 0.0
        per_sec = total / wall if wall > 0.01 else 0.0
        ratio = per_sec / req if req else 0.0
        verdict = "OK" if abs(ratio - 1.0) < 0.03 else f"x{ratio:.3f}"
        print(f"{req:>8} {total:>10} {wall:>9.3f} {per_sec:>10.0f} {verdict}")
    except Exception as exc:
        print(f"{req:>8} {'-':>10} {'-':>9} {'-':>10} ошибка: {exc}")

    time.sleep(0.4)

print()
print("Если отс/с совпадает с запросом — поток корректен.")
print("Если втрое больше — устройство игнорирует запрос (пишет 48000 вместо 16000).")