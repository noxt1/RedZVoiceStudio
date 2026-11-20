"""Проверка содержимого дубля: есть ли речь или шум/тишина.

Смотрит: RMS, пик, долю тишины, спектральный центр (для оценки «писка»).
Если спектральный центр подозрительно высокий — запись искажена.

    python tools/diag_take_content.py
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
import studio_paths as sp

samples_dir = sp.output_paths()["samples"]

try:
    import soundfile as sf
except Exception as exc:
    print("нет soundfile:", exc)
    raise SystemExit(1)

files = []
if os.path.isdir(samples_dir):
    for fn in sorted(os.listdir(samples_dir)):
        if fn.lower().startswith("take_") and fn.lower().endswith(".wav"):
            files.append(os.path.join(samples_dir, fn))

if not files:
    print("дублей нет")
    raise SystemExit(0)

print(f"{'файл':<14} {'пик':>7} {'RMS':>7} {'тишина%':>8} {'центр Гц':>9}")
print("-" * 54)

for p in files[:6]:
    data, sr = sf.read(p, dtype="float32", always_2d=False)
    if getattr(data, "ndim", 1) > 1:
        data = data.mean(axis=1)
    data = np.asarray(data, dtype=np.float32)

    peak = float(np.abs(data).max()) if data.size else 0.0
    rms = float(np.sqrt((data.astype(np.float64) ** 2).mean())) if data.size else 0.0

    # доля блоков тише -45 дБ
    win = int(sr * 0.02)
    n = len(data) // win
    if n:
        frames = data[:n * win].reshape(n, win)
        energy = np.sqrt((frames.astype(np.float64) ** 2).mean(axis=1))
        thr = max(peak * 0.02, 1e-4)
        silence = float((energy < thr).mean() * 100)
    else:
        silence = 100.0

    # спектральный центр: если много энергии на высоких частотах — «писк»
    if data.size > 1024:
        spec = np.abs(np.fft.rfft(data[:min(len(data), 1 << 15)]
                                  * np.hanning(min(len(data), 1 << 15))))
        freqs = np.fft.rfftfreq(min(len(data), 1 << 15), 1.0 / sr)
        total = float(spec.sum()) or 1.0
        centroid = float((spec * freqs).sum() / total)
    else:
        centroid = 0.0

    print(f"{os.path.basename(p):<14} {peak:>7.3f} {rms:>7.4f} "
          f"{silence:>7.1f}% {centroid:>9.0f}")

print()
print("Ориентиры для нормальной речи:")
print("  пик      0.05 – 0.9")
print("  RMS      0.01 – 0.15")
print("  тишина   10 – 60%")
print("  центр    300 – 1800 Гц  (выше 2500 Гц — писк/искажение)")