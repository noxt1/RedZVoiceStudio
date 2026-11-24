"""Метрики аудио для диагностики захвата микрофона.

Один и тот же код считает уровни и в приложении (строка лога на каждую
фразу), и в измерительном инструменте `tools/check_mic_gain.py`. Иначе
таблица замеров и реальный лог жили бы в разных единицах.

Что считается на сегменте:

  * RMS / dBFS        — средний уровень;
  * peak / dBFS       — пиковая амплитуда;
  * clipping          — доля сэмплов на пределе (|x| >= 0.99);
  * noise floor       — 10-й процентиль RMS кадров 20 мс;
  * speech level      — 90-й процентиль RMS кадров 20 мс;
  * SNR               — speech/noise в дБ (ПРИБЛИЖЕНИЕ, см. ниже);
  * speech/silence    — длительность кадров выше порога речи;
  * duration          — длительность сегмента;
  * trimmed           — сколько аудио срезано обрезкой тишины;
  * gain_*            — во сколько раз сегмент усилен/ослаблен.

SNR здесь — процентильная оценка, а не измерение по известному шуму:
шумовой пол берётся как 10-й процентиль кадров, уровень речи — как 90-й.
На записи без пауз шумовой пол завышается, поэтому значение — нижняя
граница SNR. В отчётах это указано явно.
"""

from __future__ import annotations

import json
import os
import time

import numpy as np

FRAME_SEC = 0.02
CLIP_LEVEL = 0.99


def _frames(audio: np.ndarray, sr: int, sec: float = FRAME_SEC):
    """Нарезать сигнал на кадры; последний неполный кадр отбрасывается."""
    win = max(1, int(round(sr * sec)))
    n = len(audio) // win
    if n <= 0:
        arr = np.asarray(audio, dtype=np.float64).reshape(1, -1)
        return arr
    return np.asarray(audio, dtype=np.float64)[:n * win].reshape(n, win)


def _rms(x: np.ndarray) -> float:
    if x.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(x, dtype=np.float64))))


def db(value: float) -> float:
    """Амплитуда -> dBFS (полная шкала = 1.0)."""
    return 20.0 * float(np.log10(max(float(value), 1e-9)))


def segment_metrics(audio: np.ndarray, sr: int,
                    trimmed_from: int | None = None) -> dict:
    """Уровни и длительности одного сегмента (моно, float32)."""
    x = np.asarray(audio, dtype=np.float32).reshape(-1)
    rms = _rms(x)
    peak = float(np.abs(x).max()) if x.size else 0.0
    clip = float(np.mean(np.abs(x) >= CLIP_LEVEL)) if x.size else 0.0
    frames = _frames(x, sr)
    fr = np.sqrt(np.mean(np.square(frames), axis=1)) if frames.size else \
        np.zeros(1)
    noise = float(np.percentile(fr, 10)) if fr.size else 0.0
    speech = float(np.percentile(fr, 90)) if fr.size else 0.0
    thr = max(noise * 3.0, 0.003)
    voiced = fr > thr
    snr = db(speech) - db(noise) if noise > 0 else 0.0
    return {
        "duration": round(len(x) / float(sr), 3),
        "rms": round(rms, 6),
        "rms_db": round(db(rms), 1),
        "peak": round(peak, 6),
        "peak_db": round(db(peak), 1),
        "clipping": round(clip, 5),
        "noise_floor": round(noise, 6),
        "noise_db": round(db(noise), 1),
        "speech_level": round(speech, 6),
        "snr_db": round(snr, 1),
        "speech_sec": round(float(voiced.sum()) * FRAME_SEC, 3),
        "silence_sec": round(float((~voiced).sum()) * FRAME_SEC, 3),
        "trimmed_sec": (round((trimmed_from - len(x)) / float(sr), 3)
                        if trimmed_from else 0.0),
    }


def noise_rms(audio: np.ndarray, sr: int) -> float:
    """Уровень шума комнаты по самой тихой части записи (10-й процентиль)."""
    frames = _frames(audio, sr)
    if frames.size == 0:
        return 0.0
    fr = np.sqrt(np.mean(np.square(frames), axis=1))
    return float(np.percentile(fr, 10))


class DiagLog:
    """JSONL-лог диагностики: одна строка на этап обработки фразы.

    Пишется только когда включён `AURALOOM_AUDIO_DIAG=1`: в обычной работе
    лишних файлов и работы с диском нет.
    """

    def __init__(self, path: str | None = None) -> None:
        self.path = path or ""
        self._fh = None

    @staticmethod
    def enabled() -> bool:
        return os.environ.get("AURALOOM_AUDIO_DIAG", "") not in ("", "0")

    def write(self, stage: str, metrics: dict) -> None:
        if not self.path:
            return
        try:
            if self._fh is None:
                os.makedirs(os.path.dirname(self.path), exist_ok=True)
                self._fh = open(self.path, "a", encoding="utf-8")
            row = {"t": round(time.time(), 3), "stage": stage, **metrics}
            self._fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            self._fh.flush()
        except Exception:
            pass

    def close(self) -> None:
        try:
            if self._fh is not None:
                self._fh.close()
        except Exception:
            pass
        self._fh = None
