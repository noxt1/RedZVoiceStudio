"""Замер потребления ресурсов движком перевода.

Показывает, сколько VRAM и RAM занимает движок и сколько стоит каждый
этап (распознавание / перевод / синтез) — чтобы понимать, что оптимизировать.

    "<engine>\\Scripts\\python.exe" research\\bench_resources.py
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

WS = os.path.join(os.environ.get("LOCALAPPDATA", ""), "RedZVoiceStudio", "workspace")
REF = os.path.join(WS, "reference.wav")


def gpu_mb() -> int:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15).stdout.strip()
        used, total = [int(x) for x in out.split(",")]
        return used
    except Exception:
        return 0


def rss_mb() -> float:
    try:
        import psutil
        return psutil.Process().memory_info().rss / 1e6
    except Exception:
        try:
            with open("/proc/self/statm") as fh:
                return int(fh.read().split()[1]) * 4096 / 1e6
        except Exception:
            return 0.0


def main() -> None:
    import live_translate as lt

    print(f"  VRAM до загрузки:      {gpu_mb()} МБ")
    print(f"  RAM  до загрузки:      {rss_mb():.0f} МБ")

    engine = lt.Engine()
    t0 = time.time()
    engine.load(REF)
    print(f"\n  модели загружены за {time.time() - t0:.1f} с")
    print(f"  VRAM после загрузки:  {gpu_mb()} МБ")
    print(f"  RAM  после загрузки:  {rss_mb():.0f} МБ")

    # замер этапов на реальной записи
    samples = sorted(glob.glob(os.path.join(WS, "voice_samples", "*.wav")))[:2]
    if samples:
        import soundfile as sf
        for path in samples:
            audio, sr = sf.read(path, dtype="float32", always_2d=False)
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            t0 = time.time()
            ru = engine.transcribe(
                (np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes(),
                sr, 0.0)
            t_asr = (time.time() - t0) * 1000
            t0 = time.time()
            es = engine.translate_text(ru)
            t_tr = (time.time() - t0) * 1000
            t0 = time.time()
            chunks = engine.tts.inference_stream(
                es, "es", engine.gpt_latent, engine.spk_emb,
                stream_chunk_size=10, temperature=0.75)
            total = 0.0
            for c in chunks:
                total += len(c)
            t_tts = (time.time() - t0) * 1000
            print(f"\n  «{ru}»")
            print(f"    распознавание {t_asr:6.0f} мс | перевод {t_tr:5.0f} мс"
                  f" | синтез {t_tts:6.0f} мс ({total / 24000:.1f} с звука)")
    print(f"\n  VRAM в конце:          {gpu_mb()} МБ")
    print(f"  RAM  в конце:          {rss_mb():.0f} МБ")


if __name__ == "__main__":
    main()
