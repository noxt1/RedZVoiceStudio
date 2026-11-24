"""Замер: какая модель распознавания реально быстрее и насколько точнее.

Контекст: в движке строка `ASR_MODEL = "mobiuslabsgmbh/faster-whisper-large-v3-turbo"`
перезатирает лёгкую модель, заданную строкой выше. Из-за этого «облегчённый»
режим не работает, и каждая фраза распознаётся на ~0.6 с дольше.

Этот скрипт меряет ОБЕ модели на настоящих записях пользователя
(workspace/voice_samples/*.wav) и печатает:
  * время загрузки и время распознавания;
  * распознанный текст (можно сравнить качество).

Запуск (нужен движок с torch):
    "<engine>\\Scripts\\python.exe" research\\bench_asr_models.py
"""

from __future__ import annotations

import glob
import os
import time

import numpy as np

WS = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Auraloom", "workspace")
SAMPLES = os.path.join(WS, "voice_samples")

MODELS = (
    ("Systran/faster-whisper-small", "cuda", "float16"),
    ("mobiuslabsgmbh/faster-whisper-large-v3-turbo", "cuda", "float16"),
)


def resample_to_16k(audio: np.ndarray, sr: int) -> np.ndarray:
    from math import gcd

    from scipy.signal import resample_poly

    g = gcd(int(sr), 16000)
    return resample_poly(audio, 16000 // g, int(sr) // g).astype(np.float32)


def main() -> None:
    import soundfile as sf
    from faster_whisper import WhisperModel

    files = sorted(glob.glob(os.path.join(SAMPLES, "*.wav")))
    if not files:
        print(f"нет записей в {SAMPLES}")
        return

    # читаем образцы
    clips = []
    for path in files[:6]:
        audio, sr = sf.read(path, dtype="float32", always_2d=False)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        clips.append((os.path.basename(path), resample_to_16k(audio, sr)))

    print(f"образцов: {len(clips)}\n")
    results: dict[str, list[str]] = {}

    for name, dev, ct in MODELS:
        short = name.split("/")[-1].replace("faster-whisper-", "")
        print(f"=== {short} / {dev} / {ct} ===")
        try:
            t0 = time.time()
            model = WhisperModel(name, device=dev, compute_type=ct)
            load = time.time() - t0
            print(f"  загрузка: {load:.1f} с")
            texts = []
            times = []
            for fname, audio in clips:
                t0 = time.time()
                segs, _ = model.transcribe(
                    audio, language="ru", beam_size=1, vad_filter=False,
                    condition_on_previous_text=False,
                    no_speech_threshold=0.6, log_prob_threshold=-1.0)
                items = list(segs)
                dt = time.time() - t0
                text = " ".join(s.text.strip() for s in items).strip()
                times.append(dt)
                texts.append(text)
                print(f"  {fname:<16} {dt * 1000:6.0f} мс  {text[:60]!r}")
            print(f"  среднее: {np.mean(times) * 1000:.0f} мс")
            results[short] = texts
        except Exception as exc:  # noqa: BLE001
            print(f"  ОШИБКА: {type(exc).__name__}: {exc}")
        print()
        import torch
        torch.cuda.empty_cache()

    print("=== СРАВНЕНИЕ ТЕКСТОВ ===")
    keys = list(results)
    if len(keys) == 2:
        a, b = keys
        for i, (ta, tb) in enumerate(zip(results[a], results[b])):
            same = ta.strip() == tb.strip()
            print(f"  [{i}] {'совпадает' if same else 'РАЗЛИЧАЕТСЯ'}")
            if not same:
                print(f"      {a}: {ta!r}")
                print(f"      {b}: {tb!r}")


if __name__ == "__main__":
    main()
