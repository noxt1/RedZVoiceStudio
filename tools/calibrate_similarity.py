"""Калибровка метрики похожести голоса.

Проверяет, что метрика различает:
  * тот же голос, разные фразы (Piper es-MX против Piper es-MX)
  * разные голоса (FLEURS-человек против Piper)
  * XTTS-клон против его собственного референса

    python tools\\calibrate_similarity.py
"""

from __future__ import annotations

import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import voice_similarity as vs  # noqa: E402

PAIRS = [
    ("один голос Piper, разные фразы", "out/wav/mx_01.wav", "out/wav/mx_07.wav", "same"),
    ("разные голоса (человек vs Piper)", "FLEURS", "out/wav/mx_01.wav", "diff"),
    ("XTTS-клон против своего референса", "FLEURS", "CLONE", "clone"),
]

FLEURS = r"C:\Users\cyril\AppData\Local\Temp\opencode\fleurs\ref_natural\cand.wav"
CLONE = r"C:\Users\cyril\AppData\Local\Temp\opencode\out_xtts_nat2\wav\mx_01.wav"


def resolve(path: str) -> str:
    if path == "FLEURS":
        return FLEURS
    if path == "CLONE":
        return CLONE
    return os.path.join(ROOT, path)


def main() -> None:
    profiler = vs.VoiceProfiler()

    def profile(path: str) -> tuple[np.ndarray, float, float]:
        audio, sr = vs.load_mono(path)
        return (profiler.embed(path),
                vs.f0_median(vs.resample(audio, sr, vs.SR), vs.SR),
                vs.spectral_centroid(audio, sr))

    print("Калибровка метрики:\n")
    for label, a_path, b_path, kind in PAIRS:
        a, b = resolve(a_path), resolve(b_path)
        if not (os.path.exists(a) and os.path.exists(b)):
            print(f"  --  {label:<40} файлы отсутствуют, пропуск")
            continue
        ea, f0a, ca = profile(a)
        eb, f0b, cb = profile(b)
        ecapa = float(np.dot(ea, eb))
        st = vs.semitones(f0a, f0b)
        verdict = {
            "same": "OK" if (st <= 3.5 and ecapa >= 0.25) else "!!",
            "diff": "OK" if (st > 3.5 or ecapa < 0.25) else "!!",
            "clone": "  ",
        }[kind]
        print(f"  {verdict:<2} {label:<40} ECAPA={ecapa:+.3f}  ΔF0={st:+.2f} st")


if __name__ == "__main__":
    main()
