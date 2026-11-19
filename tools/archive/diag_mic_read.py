"""Почему микрофон отдаёт нули: перебор частот и способов чтения.

    python tools\\diag_mic_read.py
"""

from __future__ import annotations

import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

import sounddevice as sd  # noqa: E402

RATES = (16000, 22050, 32000, 44100, 48000)


def read_peak(idx: int, rate: int) -> float:
    try:
        with sd.InputStream(samplerate=rate, channels=1, dtype="float32",
                            device=idx, blocksize=1024) as st:
            data, _ = st.read(int(rate * 1.0))
        if len(data) == 0:
            return -1.0
        return float(np.abs(data[:, 0]).max())
    except Exception as exc:
        return -2.0  # не открывается


def callback_peak(idx: int, rate: int, seconds: float = 1.0) -> float:
    chunks = []

    def cb(indata, frames, t, status):
        chunks.append(indata[:, 0].copy())

    try:
        with sd.InputStream(samplerate=rate, channels=1, dtype="float32",
                            device=idx, blocksize=1024, callback=cb):
            time.sleep(seconds)
    except Exception:
        return -2.0
    if not chunks:
        return -1.0
    return float(np.abs(np.concatenate(chunks)).max())


def main() -> None:
    devices = sd.query_devices()
    mics = [(i, d["name"]) for i, d in enumerate(devices) if d["max_input_channels"] > 0]
    print(f"{'idx':>4}  {'устройство':<42} {'read()':<26} callback()")
    for idx, name in mics:
        reads = {}
        cbs = {}
        for rate in RATES:
            r = read_peak(idx, rate)
            c = callback_peak(idx, rate)
            reads[rate] = r
            cbs[rate] = c
        good_r = {k: v for k, v in reads.items() if v >= 0}
        good_c = {k: v for k, v in cbs.items() if v >= 0}
        print(f"{idx:>4}  {name[:42]:<42} {str(good_r):<26} {str(good_c)}")
    print("\n-1 = данных нет, -2 = не открывается; иначе пик сигнала")


if __name__ == "__main__":
    main()
