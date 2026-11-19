"""Запись 3 секунд и подробный разбор.

Пишет файл, считает длительность по отсчётам, спектральный центр,
повторяемость (а не шум ли это). Так видно: пишет ли Recorder речь
или мусор.

    python tools/diag_record_once.py
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
out = os.path.join(out_dir, "_diag_record.wav")

dev_idx, dev_name = core.recalled_mic()
if dev_idx is None:
    dev_idx, dev_name = core.pick_input_device()
print("устройство:", dev_idx, dev_name)

# как это делает приложение
rec = core.Recorder()
rec.device = dev_idx
print("запуск Recorder...")
t0 = time.time()
rec.start(dev_idx)
print("recorder.sr =", rec.sr)
time.sleep(3.0)
raw = rec.stop()
wall = time.time() - t0

print(f"получено отсчётов: {len(raw)}")
print(f"ожидалось при {rec.sr} Гц за 3 c: {int(rec.sr * 3)}")
print(f"фактическая длительность: {len(raw) / rec.sr:.3f} c")
print(f"реальное время записи: {wall:.3f} c")

if len(raw) == 0:
    print("ПУСТО — микрофон не отдал данных")
    raise SystemExit(1)

peak = float(np.abs(raw).max())
rms = float(np.sqrt((raw.astype(np.float64) ** 2).mean()))
print(f"пик={peak:.5f}  RMS={rms:.6f}")

# спектральный центр
n = min(len(raw), 1 << 15)
seg = raw[:n] * np.hanning(n)
spec = np.abs(np.fft.rfft(seg))
freqs = np.fft.rfftfreq(n, 1.0 / rec.sr)
centroid = float((spec * freqs).sum() / (spec.sum() or 1.0))
print(f"спектральный центр: {centroid:.0f} Гц")

# сохраняем как приложение
trimmed = core.trim_by_energy(raw, rec.sr)
if rec.sr != core.SR:
    trimmed = core.resample_linear(trimmed, rec.sr, core.SR)
sf.write(out, trimmed, core.SR, subtype="PCM_16")
print(f"сохранено: {out}")
info = sf.info(out)
print(f"  частота={info.samplerate}  длительность={info.duration:.3f} c")

print()
print("Если длительность по отсчётам сильно меньше 3 c —")
print("микрофон отдаёт меньше данных, чем заявлено (главная причина «ускорения»).")