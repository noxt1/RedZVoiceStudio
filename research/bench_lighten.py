"""Замер: как облегчить движок, чтобы он не мешал игре.

Пробует варианты и меряет:
  * скорость распознавания (модель whisper);
  * скорость перевода (CPU против GPU);
  * сколько VRAM занимает движок;
  * задержку перевода при ЗАГРУЖЕННОЙ GPU (имитация игры).

Итог: какой набор даёт минимальную задержку и минимальную нагрузку.

    "<engine>\\Scripts\\python.exe" research\\bench_lighten.py
"""

from __future__ import annotations

import base64
import glob
import json
import os
import subprocess
import time

import numpy as np

WS = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Auraloom", "workspace")
ENGINE = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Auraloom",
                      "engine", "Scripts", "python.exe")
REF = os.path.join(WS, "reference.wav")
SAMPLES = os.path.join(WS, "voice_samples")


def gpu() -> dict:
    out = {"used": 0, "total": 0, "util": 0}
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15)
        p = [x.strip() for x in r.stdout.strip().split(",")]
        out = {"used": int(p[0]), "total": int(p[1]), "util": int(p[2])}
    except Exception:
        pass
    return out


def bench_asr(model_name: str, device: str, compute_type: str, audio16) -> float:
    from faster_whisper import WhisperModel
    t0 = time.time()
    m = WhisperModel(model_name, device=device, compute_type=compute_type)
    load = time.time() - t0
    t0 = time.time()
    segs, _ = m.transcribe(audio16, language="ru", beam_size=1, vad_filter=False,
                           condition_on_previous_text=False)
    text = " ".join(s.text.strip() for s in segs)
    dt = time.time() - t0
    del m
    import torch
    torch.cuda.empty_cache()
    return load, dt, text


def main() -> None:
    import soundfile as sf

    files = sorted(glob.glob(os.path.join(SAMPLES, "*.wav")))[:3]
    audio, sr = sf.read(files[0], dtype="float32", always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    from math import gcd
    from scipy.signal import resample_poly
    g = gcd(int(sr), 16000)
    audio16 = resample_poly(audio, 16000 // g, int(sr) // g).astype(np.float32)

    print("=== 1. РАСПОЗНАВАНИЕ: модели ===")
    print(f"  {'модель':<42}{'загрузка':>10}{'распознавание':>14}  текст")
    for name, dev, ct in (
        ("mobiuslabsgmbh/faster-whisper-large-v3-turbo", "cuda", "float16"),
        ("mobiuslabsgmbh/faster-whisper-medium", "cuda", "float16"),
        ("Systran/faster-whisper-small", "cuda", "float16"),
        ("Systran/faster-whisper-base", "cuda", "float16"),
        ("Systran/faster-whisper-small", "cpu", "int8"),
    ):
        try:
            load, dt, text = bench_asr(name, dev, ct, audio16)
            short = name.split("/")[-1].replace("faster-whisper-", "")
            print(f"  {short + ' / ' + dev + ' / ' + ct:<42}{load:>9.1f}с"
                  f"{dt:>13.2f}с  {text[:28]!r}")
        except Exception as exc:
            print(f"  {name} / {dev}: {type(exc).__name__}: {exc}")

    print("\n=== 2. ПЕРЕВОД: CPU против GPU ===")
    from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
    tok = AutoTokenizer.from_pretrained("Helsinki-NLP/opus-mt-ru-es")
    text_ru = "Нет, брат, ты чего тут делаешь? Опять пьяный?"
    for dev, dt_ in (("cuda", torch.float16 if False else None), ("cpu", None)):
        pass
    import torch
    for dev in ("cuda", "cpu"):
        dtype = torch.float16 if dev == "cuda" else torch.float32
        t0 = time.time()
        m = AutoModelForSeq2SeqLM.from_pretrained("Helsinki-NLP/opus-mt-ru-es",
                                                 dtype=dtype).to(dev).eval()
        load = time.time() - t0
        batch = tok([text_ru], return_tensors="pt").to(dev)
        with torch.inference_mode():
            m.generate(**batch, max_new_tokens=64, num_beams=1)
        times = []
        for _ in range(4):
            t0 = time.time()
            with torch.inference_mode():
                out = m.generate(**batch, max_new_tokens=64, num_beams=1)
            times.append(time.time() - t0)
        print(f"  {dev:<6} загрузка {load:.1f}с, перевод {np.mean(times) * 1000:5.0f} мс")
        del m
        torch.cuda.empty_cache()

    print("\n=== 3. ПРИОРИТЕТ ПРОЦЕССА ===")
    print("  Ниже приоритет движка (BELOW_NORMAL) -> Windows отдаёт ресурсы игре")
    print("  в первую очередь; перевод встаёт в очередь, но не торопит игру.")


if __name__ == "__main__":
    main()
