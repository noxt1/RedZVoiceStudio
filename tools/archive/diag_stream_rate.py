"""Проверка: сколько отсчётов реально приходит за секунду.

Ключевой тест. Если за 1 секунду приходит ~9449 отсчётов при запросе
16000 Гц — поток отдаёт данные с fractional rate, и запись
проигрывается втрое быстрее.

    python tools/diag_stream_rate.py
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

info = sd.query_devices(dev_idx)
print("заявленные частоты устройства:", info.get("default_samplerate"))
print()

for req_rate in (16000, 44100, 48000):
    got = []

    def cb(indata, frames, time_info, status, box=got):
        box.append(len(indata))

    try:
        t0 = time.time()
        with sd.InputStream(device=dev_idx, channels=1, samplerate=req_rate,
                            dtype="float32", blocksize=1024, callback=cb):
            time.sleep(1.0)
        wall = time.time() - t0

        total = sum(got)
        per_sec = total / wall if wall else 0.0
        print(f"запрос {req_rate:>6} Гц -> пришло {total:>7} отсчётов "
              f"за {wall:.2f} c = {per_sec:>8.0f} отс/с "
              f"(ожидалось {req_rate})  "
              f"{'OK' if abs(per_sec - req_rate) / req_rate < 0.05 else 'РАСХОЖДЕНИЕ'}")
    except Exception as exc:
        print(f"запрос {req_rate:>6} Гц -> ошибка: {exc}")

print()
print("Если «отс/с» заметно меньше запрошенной частоты —")
print("поток отдаёт данные медленнее, и запись звучит ускоренно.")