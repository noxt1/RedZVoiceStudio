"""Патч: замена анализа интонации на чистый numpy (без librosa).

    python tools\\patch_prosody_numpy.py
"""

from __future__ import annotations

import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "tools", "measure_prosody.py")

NEW_BLOCK = '''def estimate_f0(audio: np.ndarray, sr: int = SR,
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
'''


def main() -> None:
    with io.open(TARGET, encoding="utf-8") as fh:
        src = fh.read()

    start = src.index("def analyse(path: str) -> dict:")
    end = src.index("def main() -> None:")
    src = src[:start] + NEW_BLOCK + "\n\n" + src[end:]

    with io.open(TARGET, "w", encoding="utf-8") as fh:
        fh.write(src)
    print("анализ интонации переведён на numpy")


if __name__ == "__main__":
    main()
