"""Разбор сохранённого дубля: речь или искажённый сигнал.

Проверяет:
  * спектр (где основная энергия)
  * автокорреляцию (периодичность — признак речи)
  * петли/повторы (признак буферизации)

    python tools/diag_analyze_take.py <файл.wav>
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
import soundfile as sf
import studio_paths as sp

path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    sp.output_paths()["samples"], "_diag_record.wav")

if not os.path.exists(path):
    print("файла нет:", path)
    raise SystemExit(1)

data, sr = sf.read(path, dtype="float32", always_2d=False)
if getattr(data, "ndim", 1) > 1:
    data = data.mean(axis=1)
data = np.asarray(data, dtype=np.float32)

print("файл:", path)
print(f"частота: {sr} Гц, отсчётов: {len(data)}, "
      f"длительность: {len(data)/sr:.3f} c")
print(f"пик: {float(np.abs(data).max()):.6f}  "
      f"RMS: {float(np.sqrt((data.astype(np.float64)**2).mean())):.6f}")
print()

# 1. Спектр: распределение энергии по диапазонам
n = min(len(data), 1 << 15)
seg = data[:n] * np.hanning(n)
spec = np.abs(np.fft.rfft(seg)) ** 2
freqs = np.fft.rfftfreq(n, 1.0 / sr)
total = float(spec.sum()) or 1.0

bands = [(0, 300), (300, 1000), (1000, 3000), (3000, 6000), (6000, 12000), (12000, 24000)]
print("энергия по диапазонам:")
for lo, hi in bands:
    mask = (freqs >= lo) & (freqs < hi)
    pct = float(spec[mask].sum()) / total * 100
    if pct > 0.5:
        bar = "#" * int(pct / 2)
        print(f"  {lo:>5}-{hi:<5} Гц: {pct:>5.1f}%  {bar}")

# пиковая частота
peak_i = int(np.argmax(spec))
print(f"пиковая частота: {freqs[peak_i]:.0f} Гц")
print()

# 2. Автокорреляция на активном участке
win = int(sr * 0.05)
if len(data) > win * 2:
    # берём самый громкий участок
    nframes = len(data) // win
    frames = data[:nframes * win].reshape(nframes, win)
    energy = np.sqrt((frames.astype(np.float64) ** 2).mean(axis=1))
    loud_i = int(np.argmax(energy))
    chunk = frames[loud_i].astype(np.float64)
    chunk = chunk - chunk.mean()
    denom = float((chunk ** 2).sum()) or 1.0
    corr = np.correlate(chunk, chunk, mode="full")[len(chunk) - 1:]
    corr = corr / denom
    # ищем первый пик после начального спада
    lo = int(sr / 500)   # до 500 Гц
    hi = int(sr / 60)    # до 60 Гц
    if hi > len(corr):
        hi = len(corr) - 1
    if hi > lo:
        seg_corr = corr[lo:hi]
        peak_off = int(np.argmax(seg_corr)) + lo
        print(f"автокорреляция: пик 0.1 при сдвиге {peak_off} отсчётов "
              f"({sr/peak_off:.0f} Гц)" if peak_off else "")
        print(f"  значение корреляции: {corr[peak_off]:.3f} "
              f"(>0.3 — есть периодичность, похоже на речь)")
else:
    print("записи мало для анализа")

print()
# 3. Проверка на «ускорение»: сравним с записью, растянутой на 44100/48000
print("проверка гипотезы «записано на 48к, метка 44.1к»:")
print(f"  если бы так, длительность была бы {len(data)/48000:.3f} c")
print(f"  фактически (метка 44100): {len(data)/sr:.3f} c")