"""Измерение выразительности (интонации) реплик.

«Плоская» речь — это малый разброс высоты тона и энергии. Считаем:

  f0_med   — медианная высота тона (Гц)
  f0_std   — стандартное отклонение высоты тона (Гц)  ← «живость»
  f0_range — размах высоты тона (Гц)
  e_std    — variability энергии
  rate     — темп (фонем в секунду)

    python tools\\measure_prosody.py
    python tools\\measure_prosody.py --dir путь
"""

from __future__ import annotations

import argparse
import glob
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

SR = 16000


def estimate_f0(audio: np.ndarray, sr: int = SR,
                fmin: float = 60.0, fmax: float = 400.0) -> np.ndarray:
    """Оценка высоты тона через нормализованную автокорреляцию (без librosa)."""
    win = int(sr * 0.04)
    hop = int(sr * 0.01)
    if len(audio) < win * 2:
        return np.zeros(0, dtype=np.float32)
    lag_min = max(2, int(sr / fmax))
    lag_max = min(win - 1, int(sr / fmin))
    if lag_max <= lag_min:
        return np.zeros(0, dtype=np.float32)

    out = []
    for start in range(0, len(audio) - win, hop):
        frame = audio[start:start + win]
        if np.sqrt((frame.astype(np.float64) ** 2).mean()) < 1e-3:
            out.append(0.0)
            continue
        frame = frame - frame.mean()
        energy = float((frame.astype(np.float64) ** 2).sum())
        if energy <= 1e-9:
            out.append(0.0)
            continue
        corr = np.correlate(frame, frame, mode="full")[win - 1:win + lag_max]
        if corr.size <= lag_min:
            out.append(0.0)
            continue
        segment = corr[lag_min:]
        lag = lag_min + int(np.argmax(segment))
        out.append(sr / lag if corr[lag] > 0.3 else 0.0)
    return np.asarray(out, dtype=np.float32)


def analyse(path: str) -> dict:
    import soundfile as sf

    audio, sr = sf.read(path, dtype="float32", always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sr != SR:
        from math import gcd
        from scipy.signal import resample_poly
        g = gcd(int(sr), SR)
        audio = resample_poly(audio, SR // g, int(sr) // g).astype(np.float32)

    f0 = estimate_f0(audio, SR)
    voiced = f0[f0 > 60]
    if voiced.size < 5:
        return {"f0_med": 0.0, "f0_std": 0.0, "f0_range": 0.0, "e_std": 0.0,
                "dur": len(audio) / SR}

    win = int(SR * 0.04)
    hop = int(SR * 0.01)
    n = max(0, (len(audio) - win) // hop)
    if n:
        frames = np.lib.stride_tricks.as_strided(
            audio, shape=(n, win), strides=(audio.strides[0] * hop, audio.strides[0]))
        energy = np.sqrt((frames.astype(np.float64) ** 2).mean(axis=1))
    else:
        energy = np.zeros(0)

    return {
        "f0_med": float(np.median(voiced)),
        "f0_std": float(np.std(voiced)),
        "f0_range": float(np.percentile(voiced, 95) - np.percentile(voiced, 5)),
        "e_std": float(np.std(energy)) if energy.size else 0.0,
        "dur": len(audio) / SR,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default=os.path.join(ROOT, "out", "wav"))
    parser.add_argument("--limit", type=int, default=12)
    args = parser.parse_args()

    files = sorted(glob.glob(os.path.join(args.dir, "mx_*.wav")))
    if not files:
        sys.exit("Нет файлов:", args.dir)

    print(f"{'клип':<14}{'F0 мед':>8}{'F0 σ':>8}{'F0 разм':>10}{'E σ':>8}{'длит':>8}")
    rows = []
    for path in files[: args.limit]:
        m = analyse(path)
        rows.append(m)
        print(f"{os.path.basename(path):<14}{m['f0_med']:>8.1f}{m['f0_std']:>8.1f}"
              f"{m['f0_range']:>10.1f}{m['e_std']:>8.3f}{m['dur']:>8.2f}")

    if rows:
        print(f"\nсредние: F0 σ={np.mean([r['f0_std'] for r in rows]):.1f} Гц  "
              f"F0 размах={np.mean([r['f0_range'] for r in rows]):.1f} Гц  "
              f"E σ={np.mean([r['e_std'] for r in rows]):.3f}")
        print("больше F0 σ и F0 размах -> живее интонация")


if __name__ == "__main__":
    main()
