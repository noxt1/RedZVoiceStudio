"""Запись образца твоего голоса для клонирования (XTTS-v2).

Что нужно: 15-25 секунд твоей обычной речи, без шума и музыки.
После записи файл reference.wav кладётся рядом, и ты запускаешь:

    python tools/xtts_clone.py --reference reference.wav

Зависимости: sounddevice, numpy, soundfile.
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import soundfile as sf
import sounddevice as sd

SR = 44100

PROMPT = """
Запиши сейчас 15-25 секунд своей обычной речи.

Хороший образец:
  - спокойная речь, твой обычный тембр
  - без музыки, без шума вентилятора, без эха
  - микрофон на 15-20 см от рта
  - примерно так: "Hola, me llamo [имя], hoy es un dia tranquilo,
     estoy hablando un poco para crear una muestra de mi voz."

После записи проверь: файл должен звучать чисто и без посторонних шумов.
"""


def record(seconds: float, out_path: str, device: int | None) -> None:
    print(PROMPT)
    print(f"Запись {seconds:.0f} сек -> {out_path}\n")
    if device is not None:
        sd.query_devices()
        sd._default.device = [device, device]  # noqa: SLF001

    frames = int(seconds * SR)
    try:
        rec = sd.rec(frames, samplerate=SR, channels=1, dtype="float32")
        sd.wait()
    except KeyboardInterrupt:
        print("\nПрервано — сохраняю записанное.")
        rec = rec if "rec" in locals() else np.zeros(0, dtype="float32")

    audio = np.asarray(rec, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    peak = float(np.abs(audio).max()) if len(audio) else 0.0
    if peak > 1e-5:
        audio = audio / peak * 0.95

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    sf.write(out_path, audio, SR, subtype="PCM_16")
    dur = len(audio) / SR
    print(f"\nГотово: {out_path}  ({dur:.1f} c)")

    if dur < 6:
        print("ВНИМАНИЕ: меньше 6 секунд — XTTS будет клонировать голос плохо.")
    else:
        print("Длины достаточно для клонирования.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=18.0)
    parser.add_argument("--out", default="reference.wav")
    parser.add_argument("--device", type=int, default=None, help="индекс устройства ввода")
    args = parser.parse_args()
    record(args.seconds, args.out, args.device)


if __name__ == "__main__":
    main()
