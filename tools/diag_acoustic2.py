"""Диагностика акустики (правильная): тон в динамики -> микрофон слышит.

Важно: читать микрофон нужно через callback (у части устройств st.read()
отдаёт нули, а callback — реальные данные).

    python tools\\diag_acoustic2.py
"""

from __future__ import annotations

import os
import sys
import threading
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

import audiodev  # noqa: E402
import sounddevice as sd  # noqa: E402

SR = 48000


def capture_peak(mic_i: int, rate: int, seconds: float,
                 play_fn=None) -> tuple[float, np.ndarray]:
    chunks = []

    def cb(indata, frames, t, status):
        chunks.append(indata[:, 0].copy())

    with sd.InputStream(samplerate=rate, channels=1, dtype="float32",
                        device=mic_i, blocksize=1024, callback=cb):
        if play_fn:
            play_fn()
        time.sleep(seconds)
    if not chunks:
        return 0.0, np.zeros(0, dtype=np.float32)
    audio = np.concatenate(chunks)
    return float(np.abs(audio).max()), audio


def main() -> None:
    mic_i = 27   # Микрофон (2- fifine Microphone) — работает на 48 кГц
    mic_name = "Микрофон (2- fifine Microphone) #27"
    rate = audiodev.best_rate(mic_i, "input", 48000)
    print(f"микрофон: {mic_name}, частота {rate} Гц\n")

    # 1. шумовой пол
    peak, _ = capture_peak(mic_i, rate, 1.2)
    print(f"1. шумовой пол микрофона: {peak:.5f}")

    # 2. тон в динамики
    devices = sd.query_devices()
    outs = [(i, d["name"]) for i, d in enumerate(devices)
            if d["max_output_channels"] > 0]
    seen = set()
    tone = (0.95 * np.sin(2 * np.pi * 1000 * np.arange(int(SR * 1.2)) / SR)).astype("float32")
    print()
    for i, name in outs:
        key = name.split("(")[0].strip()
        if key in seen:
            continue
        seen.add(key)
        if not audiodev.working_rates(i, "output"):
            continue
        try:
            peak, _ = capture_peak(mic_i, rate, 1.6,
                                   play_fn=lambda idx=i: sd.play(tone, samplerate=SR, device=idx))
        except Exception as exc:  # noqa: BLE001
            print(f"2. {name[:44]:<46} ошибка {exc}")
            continue
        mark = "СЛЫШНО" if peak > 0.02 else "тихо "
        print(f"2. {name[:44]:<46} пик {peak:.4f}  {mark}")


if __name__ == "__main__":
    main()
