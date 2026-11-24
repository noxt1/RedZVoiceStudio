"""Проверка готовых звуковых подсказок: уровни, длительности, целостность."""
import json
import os
import sys

import numpy as np
import soundfile as sf

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

D = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "voices", "prompts")

m = json.load(open(os.path.join(D, "manifest.json"), encoding="utf-8"))
print("voice:", m["voice"], "| license:", m["license"])
print("items:", len(m["items"]))
bad = 0
for it in m["items"]:
    a, sr = sf.read(os.path.join(D, it["file"]), dtype="float32")
    peak = float(np.abs(a).max())
    rms = float(np.sqrt((a.astype(np.float64) ** 2).mean()))
    nan = bool(np.isnan(a).any())
    ok = (not nan) and peak > 0.05 and rms > 0.01 and len(a) / sr > 1.0
    if not ok:
        bad += 1
    print(f"{'OK ' if ok else 'BAD'} {it['file']}  {len(a)/sr:5.2f}s  "
          f"sr={sr}  peak={peak:.3f}  rms={rms:.4f}  nan={nan}  "
          f"{it['emotion']:10} {it['emotion_label']}")
print()
print("плохих:", bad)
