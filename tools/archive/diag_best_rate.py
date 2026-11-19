"""Почему best_rate() возвращает неверную частоту.

best_rate перебирает CANDIDATE_RATES и берёт ПЕРВУЮ, на которой
поток открылся. Но «открылся» не значит «отдаёт речь»: на 16000
fifine открывается и отдаёт почти тишину.

Проверяем, какие частоты реально дают сигнал.

    python tools/diag_best_rate.py
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
from audiodev import CANDIDATE_RATES, _test_input

dev_idx, dev_name = core.recalled_mic()
print("устройство:", dev_idx, dev_name)
print()

info = sd.query_devices(dev_idx)
print("default_samplerate:", info.get("default_samplerate"))
print()

print("проверка каждой частоты (по 0.5 c, смотрим и открытие, и сигнал):")
print(f"{'частота':>8}  {'открытие':>10}  {'RMS':>10}  {'вердикт'}")
print("-" * 52)

for rate in CANDIDATE_RATES:
    opened = _test_input(dev_idx, rate)
    if not opened:
        print(f"{rate:>8}  {'нет':>10}  {'-':>10}  не открывается")
        continue

    got = []
    def cb(indata, frames, time_info, status, box=got):
        if status:
            return
        box.append(indata[:, 0].copy())

    try:
        import time
        with sd.InputStream(device=dev_idx, channels=1, samplerate=rate,
                            dtype="float32", blocksize=1024, callback=cb):
            time.sleep(0.5)
        if got:
            data = np.concatenate(got)
            rms = float(np.sqrt((data.astype(np.float64) ** 2).mean()))
            verdict = "тишина" if rms < 0.0005 else "сигнал есть"
        else:
            rms = 0.0
            verdict = "нет данных"
        print(f"{rate:>8}  {'да':>10}  {rms:>10.6f}  {verdict}")
    except Exception as exc:
        print(f"{rate:>8}  {'ошибка':>10}  {exc}")

print()
print("best_rate() вернёт ПЕРВУЮ открывшуюся частоту —", core.__dict__.get("SR"))
from audiodev import best_rate
print("best_rate(dev) =", best_rate(dev_idx, "input", core.SR))