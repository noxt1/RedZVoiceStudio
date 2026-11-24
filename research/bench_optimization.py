"""Замер: как уменьшить расход ресурсов движка и чем за это платить.

Движок держит три модели:
  * Whisper large-v3-turbo — распознавание, ~2.2 ГБ VRAM;
  * opus-mt-ru-es — перевод, на CPU (VRAM не занимает);
  * XTTS-v2 — синтез, ~1.8 ГБ VRAM.

Проверяем варианты экономии и их цену (скорость и качество текста):
  1. Whisper с int8_float16 (квантование) — VRAM меньше, скорость выше;
  2. Whisper small вместо turbo — VRAM меньше сильно, но текст хуже;
  3. XTTS в fp16 — VRAM меньше вдвое.

    "<engine>\\Scripts\\python.exe" research\\bench_optimization.py
"""

from __future__ import annotations

import glob
import os
import subprocess
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import prosody  # noqa: E402

WS = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Auraloom", "workspace")
REF = os.path.join(WS, "reference.wav")


def vram() -> int:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15).stdout.strip()
        return int(out.split("\n")[0])
    except Exception:
        return 0


def main() -> None:
    import soundfile as sf
    from faster_whisper import WhisperModel

    clips = []
    for path in sorted(glob.glob(os.path.join(WS, "voice_samples", "*.wav")))[:3]:
        a, sr = sf.read(path, dtype="float32", always_2d=False)
        if a.ndim > 1:
            a = a.mean(axis=1)
        # ВАЖНО: faster-whisper трактует вход как 16 кГц. Без ресемплинга
        # модель слышит мусор и выдаёт галлюцинации.
        if sr != 16000:
            from math import gcd

            from scipy.signal import resample_poly
            g = gcd(int(sr), 16000)
            a = resample_poly(a, 16000 // g, int(sr) // g).astype(np.float32)
        clips.append((os.path.basename(path), a, 16000))

    print(f"  {'модель':<34}{'VRAM':>9}{'ASR мс':>9}  распознано")
    variants = [
        ("turbo / float16 (сейчас)",
         "mobiuslabsgmbh/faster-whisper-large-v3-turbo", "float16"),
        ("turbo / int8_float16",
         "mobiuslabsgmbh/faster-whisper-large-v3-turbo", "int8_float16"),
        ("medium / float16", "Systran/faster-whisper-medium", "float16"),
        ("small / float16", "Systran/faster-whisper-small", "float16"),
        ("base / int8_float16", "Systran/faster-whisper-base", "int8_float16"),
    ]
    for label, model_id, compute in variants:
        before = vram()
        t0 = time.time()
        try:
            model = WhisperModel(model_id, device="cuda",
                                 compute_type=compute)
        except Exception as exc:
            print(f"  {label:<34} ОШИБКА {type(exc).__name__}: {exc}")
            continue
        load = time.time() - t0
        after = vram()
        times, texts = [], []
        for _fname, audio, sr in clips:
            t0 = time.time()
            segs, _ = model.transcribe(audio, language="ru", beam_size=1,
                                       vad_filter=False,
                                       condition_on_previous_text=False)
            heard = " ".join(s.text.strip() for s in segs).strip()
            times.append((time.time() - t0) * 1000)
            texts.append(heard)
        print(f"  {label:<34}{after - before:>7} МБ{np.mean(times):>9.0f}  "
              f"{texts[0][:44]!r}")
        del model
        import torch
        torch.cuda.empty_cache()
        time.sleep(1)


if __name__ == "__main__":
    main()
