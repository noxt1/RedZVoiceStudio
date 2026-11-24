"""Замер: какой образец голоса звучит живее.

XTTS клонирует не только тембр, но и ПРОСОДИЮ (интонацию). Если
образец записан монотонно (что обычно при чтении с листа), клон тоже
будет «читать с листа».

Идея: выбрать самый выразительный образец из voice_samples и
использовать его как референс для живого перевода.

    "<engine>\\Scripts\\python.exe" research\\bench_reference_tone.py
"""

from __future__ import annotations

import glob
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import prosody  # noqa: E402

WS = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Auraloom", "workspace")
SAMPLES = os.path.join(WS, "voice_samples")
REF = os.path.join(WS, "reference.wav")


def main() -> None:
    import soundfile as sf

    files = sorted(glob.glob(os.path.join(SAMPLES, "*.wav")))
    if REF and os.path.exists(REF):
        files.append(REF)
    if not files:
        print(f"нет образцов в {SAMPLES}")
        return

    print("=== просодия образцов (чем больше F0 σ и размах — тем живее) ===")
    print(f"  {'файл':<20}{'сек':>6}{'F0 σ':>9}{'размах':>9}{'RMS':>9}")
    rows = []
    for path in files:
        try:
            audio, sr = sf.read(path, dtype="float32", always_2d=False)
        except Exception as exc:
            print(f"  {os.path.basename(path)}: {exc}")
            continue
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        dur = len(audio) / sr
        f0_std = prosody.f0_spread(audio, sr)
        f0_range = prosody.f0_range(audio, sr)
        rms = float(np.sqrt((audio.astype(np.float64) ** 2).mean()))
        rows.append((os.path.basename(path), dur, f0_std, f0_range, rms))
        print(f"  {os.path.basename(path):<20}{dur:>6.1f}{f0_std:>9.1f}"
              f"{f0_range:>9.0f}{rms:>9.4f}")

    if rows:
        best = max(rows, key=lambda r: r[2])
        cur = [r for r in rows if r[0] == "reference.wav"]
        print(f"\n  самый выразительный: {best[0]} (F0 σ={best[2]:.1f})")
        if cur:
            print(f"  текущий reference.wav: F0 σ={cur[0][2]:.1f}")
            if best[2] > cur[0][2] * 1.25:
                print("  -> образец заметно живее текущего: его стоит "
                      "использовать как референс")
            else:
                print("  -> разница небольшая, референс менять не обязательно")


if __name__ == "__main__":
    main()
