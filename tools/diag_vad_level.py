"""Замер реального уровня микрофона и проверка порога VAD."""

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

import live_tab as lt

MIC = 1
SR = 44100

print(f"порог SPEECH_MIN_ABS = {lt.SPEECH_MIN_ABS}")
print(f"порог SPEECH_OVER_FLOOR = {lt.SPEECH_OVER_FLOOR}")
print(f"блок {int(SR * lt.BLOCK_SEC)} отсчётов")
print()

blocks = []

def cb(indata, frames, time_info, status):
    blocks.append(indata[:, 0].copy())

print("говори 3 секунды…")
with sd.InputStream(device=MIC, channels=1, samplerate=SR,
                    dtype="float32", blocksize=int(SR * lt.BLOCK_SEC),
                    callback=cb):
    time.sleep(3.0)

if not blocks:
    print("нет данных с микрофона")
    raise SystemExit(1)

rms_list = [float(np.sqrt((b.astype(np.float64) ** 2).mean())) for b in blocks]
print(f"блоков: {len(rms_list)}")
print(f"RMS: min={min(rms_list):.5f} max={max(rms_list):.5f} "
      f"avg={sum(rms_list)/len(rms_list):.5f}")
print()

floor = float(np.percentile(rms_list, 20))
thr = max(floor * lt.SPEECH_OVER_FLOOR, lt.SPEECH_MIN_ABS)
print(f"шумовой пол (20-й перцентиль): {floor:.5f}")
print(f"порог VAD: {thr:.5f}")
print()

loud = [r for r in rms_list if r > thr]
print(f"блоков выше порога: {len(loud)} из {len(rms_list)}")
if not loud:
    print()
    print("ПРОБЛЕМА: ни один блок не превысил порог.")
    print("Речь не будет распознана — VAD не сработает.")
    print()
    print("Причина: SPEECH_MIN_ABS слишком высокий для этого микрофона.")
else:
    print("порог проходится — VAD должен работать")