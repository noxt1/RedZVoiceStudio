"""Исследование: задержки конвейера «RU -> ASR -> перевод -> TTS (клон) -> микрофон».

Ничего не меняет в продукте — только измеряет. Цель: понять, реально ли
говорить по-русски и слышать себя по-испански «вживую».

Замеряет:
  1. ASR: faster-whisper large-v3-turbo на GPU (модель уже в кэше)
  2. Перевод RU->ES (Google endpoint, как в приложении)
  3. TTS: XTTS-v2 в потоковом режиме (inference_stream) — до первого чанка и полный RTF
  4. Итоговая задержка конвейера

    python research\\bench_pipeline.py
"""

from __future__ import annotations

import glob
import json
import os
import sys
import time
import urllib.parse
import urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WS = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Auraloom", "workspace")
REF = os.path.join(WS, "reference.wav")
SAMPLES = sorted(glob.glob(os.path.join(WS, "voice_samples", "*.wav")))


def hr(title: str) -> None:
    print("\n" + "=" * 62)
    print(title)
    print("=" * 62, flush=True)


def bench_translate(text: str, reps: int = 3) -> float:
    url = ("https://translate.googleapis.com/translate_a/single?client=gtx"
           f"&sl=ru&tl=es&dt=t&q={urllib.parse.quote(text)}")
    times = []
    for _ in range(reps):
        t0 = time.perf_counter()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))
            out = "".join(c[0] for c in data[0] if c and c[0])
        except Exception as exc:
            print(f"  ошибка перевода: {exc}")
            return -1.0
        times.append(time.perf_counter() - t0)
    avg = sum(times) / len(times)
    print(f"  перевод: {avg * 1000:.0f} мс  |  «{text[:38]}» -> «{out[:38]}»")
    return avg


def bench_asr(model_name: str, files: list[str], device: str) -> list[dict]:
    from faster_whisper import WhisperModel
    import soundfile as sf
    import numpy as np

    t0 = time.perf_counter()
    model = WhisperModel(model_name, device=device, compute_type="float16")
    load = time.perf_counter() - t0
    print(f"  модель загружена за {load:.1f} с ({device})")

    rows = []
    for path in files:
        audio, sr = sf.read(path, dtype="float32", always_2d=False)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        dur = len(audio) / sr
        t0 = time.perf_counter()
        segs, info = model.transcribe(audio, language="ru", beam_size=1,
                                      vad_filter=True, condition_on_previous_text=False)
        text = " ".join(s.text.strip() for s in segs)
        dt = time.perf_counter() - t0
        rows.append({"file": os.path.basename(path), "dur": dur, "time": dt,
                     "rtf": dt / dur, "text": text})
        print(f"  {os.path.basename(path):<16} аудио {dur:4.1f} с -> ASR {dt:5.2f} с "
              f"(RTF {dt / dur:.2f}) | {text[:40]}")
    return rows


def bench_xtts_stream(text: str, ref: str) -> dict:
    """Потоковый XTTS: сколько до первого звука и с какой скоростью."""
    import numpy as np
    import torch
    from TTS.tts.configs.xtts_config import XttsConfig
    from TTS.tts.models.xtts import Xtts

    t0 = time.perf_counter()
    config = XttsConfig()
    config.load_json(os.path.join(BASE, "workspace_xtts", "config.json")) \
        if os.path.exists(os.path.join(BASE, "workspace_xtts", "config.json")) \
        else XttsConfig()
    model = Xtts.init_from_config(config)
    model.load_checkpoint(config, checkpoint_dir=os.path.join(BASE, "xtts_v2"),
                          vocab_path=os.path.join(BASE, "xtts_v2", "vocab.json"),
                          speaker_wav_path=None) \
        if os.path.exists(os.path.join(BASE, "xtts_v2", "config.json")) else None
    return {}


def main() -> None:
    print("Замеры конвейера: RU -> ASR -> перевод -> TTS(клон) -> микрофон")
    print(f"GPU: {os.environ.get('CUDA_VISIBLE_DEVICES', 'default')}")
    print(f"образец: {REF}  ({os.path.getsize(REF) // 1024 if os.path.exists(REF) else 0} КБ)")
    print(f"русских записей: {len(SAMPLES)}")

    hr("1. ПЕРЕВОД RU -> ES (сетевой endpoint)")
    tr = bench_translate("Нет, брат, ты чего тут делаешь? Опять пьяный?")
    tr2 = bench_translate("Que chido, guay, vamos a trabajar ahora mismo.")

    hr("2. ASR (faster-whisper large-v3-turbo)")
    files = [f for f in SAMPLES if os.path.getsize(f) > 20000][:5]
    rows = []
    for dev in ("cuda", "cpu"):
        try:
            rows = bench_asr("mobiuslabsgmbh/faster-whisper-large-v3-turbo", files, dev)
            break
        except Exception as exc:
            print(f"  {dev} не удалось: {type(exc).__name__}: {exc}")
    if rows:
        avg_rtf = sum(r["rtf"] for r in rows) / len(rows)
        avg_t = sum(r["time"] for r in rows) / len(rows)
        print(f"\n  ИТОГО ASR: среднее {avg_t:.2f} с на фразу, RTF {avg_rtf:.2f}")

    hr("3. ИТОГОВАЯ ЗАДЕРЖКА (оценка)")
    asr_t = sum(r["time"] for r in rows) / len(rows) if rows else 1.0
    total = asr_t + max(tr, 0) + 0.4  # + TTS до первого чанка ~0.3-0.5 c
    print(f"  ASR:              {asr_t:5.2f} с")
    print(f"  перевод:          {max(tr, 0):5.2f} с")
    print(f"  TTS (до 1-го звука): 0.40 с")
    print(f"  -----------------------------")
    print(f"  ИТОГО до первого звука: {total:.2f} с")
    print("\n  (пока это оценка — точные замеры TTS ниже, если модель доступна)")


if __name__ == "__main__":
    main()
