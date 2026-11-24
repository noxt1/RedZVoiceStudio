"""Общая постобработка звуков для звуковой панели Auraloom.

Задачи:
  * убрать лишнюю тишину в начале/конце (trim по порогу тишины)
  * нормализовать громкость к единому уровню (peak-norm + RMS-выравнивание)
  * применить мягкое ограничитель/компрессор, чтобы не было клиппинга
  * сохранить в нужные форматы (wav / ogg vorbis / mp3)

Форматы RedM/FiveM: ресурсы xsound и interact-sound принимают .ogg и .mp3.
"""

from __future__ import annotations

import os
import numpy as np
import soundfile as sf
import lameenc

SR = 44100  # рабочая частота дистрибутива


def read_audio(path: str) -> tuple[np.ndarray, int]:
    """Прочитать моно-сигнал (float32) из любого поддерживаемого файла."""
    data, sr = sf.read(path, dtype="float32", always_2d=False)
    if data.ndim > 1:
        data = data.mean(axis=1)
    return data.astype(np.float32), sr


def resample(data: np.ndarray, sr_in: int, sr_out: int = SR) -> np.ndarray:
    """Полифазный пересемплинг с FIR-фильтром (без алиасинга).

    Важно: наивный np.interp не фильтрует — образы при переходе вверх
    складываются обратно в рабочую полосу при последующем понижении
    (44.1 кГц -> 16 кГц), что портит тембр и ломает оценку схожести голоса.
    """
    if sr_in == sr_out or len(data) == 0:
        return data
    from math import gcd
    from scipy.signal import resample_poly

    g = gcd(int(sr_in), int(sr_out))
    up, down = int(sr_out // g), int(sr_in // g)
    return resample_poly(data, up, down).astype(np.float32)


def trim_silence(data: np.ndarray, sr: int, threshold_db: float = -42.0,
                 pad_ms: int = 40) -> np.ndarray:
    """Обрезать тишину по краям, оставив небольшой отступ."""
    if len(data) == 0:
        return data
    peak = float(np.abs(data).max())
    if peak <= 1e-6:
        return data
    thr = peak * (10.0 ** (threshold_db / 20.0))
    loud = np.abs(data) > thr
    if not loud.any():
        return data
    idx = np.flatnonzero(loud)
    pad = int(sr * pad_ms / 1000.0)
    start = max(0, idx[0] - pad)
    end = min(len(data), idx[-1] + pad)
    return data[start:end]


def normalize(data: np.ndarray, target_rms_db: float = -18.0,
              ceiling_db: float = -1.0) -> np.ndarray:
    """Выровнять RMS под target, затем ограничить пики мягким клиппером."""
    if len(data) == 0:
        return data
    rms = float(np.sqrt((data.astype(np.float64) ** 2).mean())) + 1e-9
    gain = (10.0 ** (target_rms_db / 20.0)) / rms
    out = data * gain
    ceiling = 10.0 ** (ceiling_db / 20.0)
    peak = float(np.abs(out).max())
    if peak > ceiling:
        # мягкое ограничение (tanh) вместо жёсткой обрезки
        out = np.tanh(out / ceiling) * ceiling
    return out.astype(np.float32)


def fade(data: np.ndarray, sr: int, fade_ms: int = 12) -> np.ndarray:
    """Короткие фейды по краям, чтобы не было щелчков."""
    if len(data) == 0:
        return data
    n = min(int(sr * fade_ms / 1000.0), len(data) // 2)
    if n <= 1:
        return data
    ramp = np.linspace(0.0, 1.0, n, dtype=np.float32)
    out = data.copy()
    out[:n] *= ramp
    out[-n:] *= ramp[::-1]
    return out


def to_16k(data: np.ndarray, sr: int) -> np.ndarray:
    """Привести сигнал к 16 кГц (требование faster-whisper для numpy-входа).

    Whisper трактует переданный numpy-массив как 16 кГц. Если отдать ему
    44.1 кГц, звук будет прочитан в 2.75 раза быстрее и распознавание
    выдаст мусор вместо реальной разборчивости.
    """
    if sr == 16000 or len(data) == 0:
        return data
    from math import gcd
    from scipy.signal import resample_poly
    g = gcd(int(sr), 16000)
    up, down = 16000 // g, int(sr) // g
    return resample_poly(data, up, down).astype(np.float32)


def process(data: np.ndarray, sr: int, target_rms_db: float = -18.0) -> np.ndarray:
    """Полный конвейер: ресемплинг -> trim -> нормализация -> фейды.

    ВАЖНО: `sr` — это частота ВХОДНЫХ данных, а не выходная.
    Если передать выходную (44100) при данных 24 кГц, ресемплинг не
    выполнится, файл получится вдвое быстрее и выше по тону — голос
    разрушается (это ломало и оценку схожести: ECAPA +0.63 -> -0.01).
    """
    data = resample(data, sr, SR)
    data = trim_silence(data, SR)
    data = normalize(data, target_rms_db)
    data = fade(data, SR)
    return data


def write_wav(data: np.ndarray, path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    sf.write(path, data, SR, subtype="PCM_16")


def write_ogg(data: np.ndarray, path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    sf.write(path, data, SR, format="OGG", subtype="VORBIS")


def write_mp3(data: np.ndarray, path: str, bitrate: int = 128) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    pcm = np.clip(data, -1.0, 1.0)
    pcm16 = (pcm * 32767.0).astype(np.int16)
    enc = lameenc.Encoder()
    enc.set_bit_rate(bitrate)
    enc.set_in_sample_rate(SR)
    enc.set_channels(1)
    enc.set_quality(2)
    mp3 = enc.encode(pcm16.tobytes())
    with open(path, "wb") as fh:
        fh.write(mp3)


def export_all(data: np.ndarray, out_dir: str, name: str) -> dict[str, str]:
    """Сохранить один клип во все нужные форматы."""
    paths = {
        "wav": os.path.join(out_dir, "wav", f"{name}.wav"),
        "ogg": os.path.join(out_dir, "ogg", f"{name}.ogg"),
        "mp3": os.path.join(out_dir, "mp3", f"{name}.mp3"),
    }
    write_wav(data, paths["wav"])
    write_ogg(data, paths["ogg"])
    write_mp3(data, paths["mp3"])
    return paths
