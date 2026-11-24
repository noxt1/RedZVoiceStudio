"""Сравнение выразительности интонации: наборы с разной «живостью».

Генерирует несколько реплик на разных уровнях --expressiveness и сравнивает
разброс высоты тона (F0 σ) и размах.

    python tools\\compare_expressiveness.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import prosody  # noqa: E402

BASE = r"C:\Users\cyril\AppData\Local\Auraloom"
ENGINE = os.path.join(BASE, "engine", "Scripts", "python.exe")
WS = os.path.join(BASE, "workspace")
REF = os.path.join(WS, "reference.wav")
CLONE = os.path.join(WS, "tools", "xtts_clone.py")

TEXTS = ["Que chido, guay!", "No manches, guay!", "Orale, carnal!", "A huevo!"]


def build(level: int, out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    for i, text in enumerate(TEXTS):
        subprocess.run([ENGINE, CLONE, "--reference", REF, "--text", text,
                        "--id", f"{i + 1:02d}", "--attempts", "3",
                        "--expressiveness", str(level), "--out", out_dir],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")


def stats(out_dir: str) -> tuple[float, float, float]:
    import glob
    import soundfile as sf
    sigmas, ranges, durs = [], [], []
    for path in sorted(glob.glob(os.path.join(out_dir, "wav", "mx_*.wav"))):
        audio, sr = sf.read(path, dtype="float32", always_2d=False)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        sigmas.append(prosody.f0_spread(audio, sr))
        ranges.append(prosody.f0_range(audio, sr))
        durs.append(len(audio) / sr)
    if not sigmas:
        return 0.0, 0.0, 0.0
    return sum(sigmas) / len(sigmas), sum(ranges) / len(ranges), sum(durs) / len(durs)


def main() -> None:
    tmp = os.path.join(BASE, "workspace", "express_test")
    results = []
    for level in (0, 2, 3):
        out_dir = os.path.join(tmp, f"lvl{level}")
        shutil.rmtree(out_dir, ignore_errors=True)
        print(f"генерирую уровень {level} ...", flush=True)
        build(level, out_dir)
        s, r, d = stats(out_dir)
        results.append((level, s, r, d))
        print(f"   уровень {level}: F0 σ={s:.1f} Гц  размах={r:.1f} Гц  "
              f"длитность={d:.2f} с")

    print("\nитог: чем выше уровень, тем больше F0 σ -> живее интонация")
    base = results[0][1] if results else 0
    for level, s, r, d in results:
        delta = (s - base) / base * 100 if base else 0
        print(f"   уровень {level}: F0 σ={s:6.1f} ({delta:+.0f}% к уровню 0)")


if __name__ == "__main__":
    main()
