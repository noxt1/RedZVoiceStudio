"""Проверка ИСПРАВЛЕННОГО пути записи (как в _stop_rec).

Записывает через Recorder, сохраняет как приложение и проверяет,
что частота файла совпадает с частотой потока.

    python tools/diag_record_fixed.py
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
import soundfile as sf

import studio_core as core
import studio_paths as sp

out_dir = sp.output_paths()["samples"]
os.makedirs(out_dir, exist_ok=True)

dev_idx, dev_name = core.recalled_mic()
print("устройство:", dev_idx, dev_name)

rec = core.Recorder()
rec.device = dev_idx
rec.start(dev_idx)
print("recorder.sr =", rec.sr)
time.sleep(3.0)
raw = rec.stop()

print(f"отсчётов: {len(raw)}")
print(f"длительность по recorder.sr: {len(raw)/rec.sr:.3f} c")

# --- точно как в _stop_rec (после исправления) ---
trimmed = core.trim_by_energy(raw, rec.sr)
rep = core.quality_report(trimmed, rec.sr)
path = os.path.join(out_dir, "_diag_fixed.wav")
sf.write(path, trimmed, rec.sr, subtype="PCM_16")

info = sf.info(path)
print()
print("=== файл ===")
print(f"частота: {info.samplerate} (поток был {rec.sr})")
print(f"отсчётов: {info.frames}")
print(f"длительность: {info.duration:.3f} c")
print(f"пик: {rep['peak']:.5f}  RMS: {rep['rms']:.6f}")
print(f"вердикт quality_report: ok={rep['ok']}  {rep['reason']}")

print()
if info.samplerate == rec.sr:
    print("OK: частота файла совпадает с частотой потока — ускорения не будет")
else:
    print("ПРОБЛЕМА: частоты различаются — запись будет искажена")

# спектральный центр готового файла
data, sr = sf.read(path, dtype="float32")
n = min(len(data), 1 << 15)
seg = data[:n] * np.hanning(n)
spec = np.abs(np.fft.rfft(seg))
freqs = np.fft.rfftfreq(n, 1.0 / sr)
centroid = float((spec * freqs).sum() / (spec.sum() or 1.0))
print(f"спектральный центр файла: {centroid:.0f} Гц (норма речи 300-1800)")