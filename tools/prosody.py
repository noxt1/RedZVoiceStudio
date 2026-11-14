"""Выразительность речи: оценка разброса высоты тона (без librosa).

«Плоская» озвучка — маленький разброс F0. Нужен объективный критерий,
чтобы при авто-починке XTTS выбирать не только «разборчиво», но и «живо».
"""

from __future__ import annotations

import numpy as np


def estimate_f0(audio: np.ndarray, sr: int, fmin: float = 60.0,
                fmax: float = 400.0) -> np.ndarray:
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
        frame = np.asarray(audio[start:start + win], dtype=np.float32)
        if float(np.sqrt((frame.astype(np.float64) ** 2).mean())) < 1e-3:
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


def f0_spread(audio: np.ndarray, sr: int) -> float:
    """Стандартное отклонение высоты тона (Гц). Больше — живее интонация."""
    f0 = estimate_f0(audio, sr)
    voiced = f0[f0 > 60]
    if voiced.size < 4:
        return 0.0
    return float(np.std(voiced))


def f0_range(audio: np.ndarray, sr: int) -> float:
    f0 = estimate_f0(audio, sr)
    voiced = f0[f0 > 60]
    if voiced.size < 4:
        return 0.0
    return float(np.percentile(voiced, 95) - np.percentile(voiced, 5))
