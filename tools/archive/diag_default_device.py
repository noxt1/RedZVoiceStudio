"""Воспроизводит ТОЧНО путь записи приложения: recorder.start(None).

Если device=None, best_rate возвращает fallback (SR=44100), поток
открывается на устройстве ПО УМОЛЧАНИЮ.

    python tools/diag_default_device.py
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

print("=== устройство по умолчанию ===")
try:
    print("sd.default.device =", sd.default.device)
    din = sd.default.device[0]
    if din is not None:
        d = sd.query_devices(din)
        print(f"  in  [{din}] {d['name']}  "
              f"каналов={d['max_input_channels']}  "
              f"default_rate={d.get('default_samplerate')}")
except Exception as exc:
    print("ошибка:", exc)
    din = None

print()
print("=== best_rate(None) ===")
from audiodev import best_rate
r = best_rate(None, "input", core.SR)
print("best_rate(None, 'input', SR) =", r)

print()
print("=== запись как в приложении (device=None) ===")
rec = core.Recorder()
rec.device = None
try:
    rec.start(None)
    print("recorder.sr =", rec.sr)
    time.sleep(2.5)
    raw = rec.stop()
    print("отсчётов:", len(raw))
    print(f"длительность по recorder.sr: {len(raw)/rec.sr:.3f} c")

    if len(raw):
        peak = float(np.abs(raw).max())
        rms = float(np.sqrt((raw.astype(np.float64) ** 2).mean()))
        print(f"пик={peak:.5f}  RMS={rms:.6f}")

        out = os.path.join(sp.output_paths()["samples"], "_diag_default.wav")
        sf.write(out, raw, rec.sr, subtype="PCM_16")
        i = sf.info(out)
        print(f"файл: частота={i.samplerate}  длительность={i.duration:.3f} c")
        print(f"  -> {out}")

        if i.samplerate == rec.sr:
            print("OK: частота совпадает")
        else:
            print("РАСХОЖДЕНИЕ частот")
except Exception as exc:
    print("ошибка записи:", exc)

print()
print("=== сравнение с явным микрофоном (fifine) ===")
rec2 = core.Recorder()
rec2.device = 1
try:
    rec2.start(1)
    print("recorder.sr =", rec2.sr)
    time.sleep(2.0)
    raw2 = rec2.stop()
    if len(raw2):
        rms2 = float(np.sqrt((raw2.astype(np.float64) ** 2).mean()))
        print(f"отсчётов: {len(raw2)}  RMS={rms2:.6f}")
        out2 = os.path.join(sp.output_paths()["samples"], "_diag_fifine.wav")
        sf.write(out2, raw2, rec2.sr, subtype="PCM_16")
        i2 = sf.info(out2)
        print(f"файл: частота={i2.samplerate}  длительность={i2.duration:.3f} c")
except Exception as exc:
    print("ошибка:", exc)