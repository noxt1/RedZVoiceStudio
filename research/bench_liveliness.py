"""Замер: какие параметры XTTS дают ЖИВУЮ подачу, а не «чтение с листа».

Берём одну и ту же фразу и синтезируем с разными настройками.
Меряем:
  * просодию  (F0 σ, размах) — чем больше, тем живее;
  * разборчивость (Whisper) — чтобы не превратить фразу в кашу;
  * длительность.

    "<engine>\\Scripts\\python.exe" research\\bench_liveliness.py
"""

from __future__ import annotations

import glob
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import prosody  # noqa: E402

WS = os.path.join(os.environ.get("LOCALAPPDATA", ""), "RedZVoiceStudio", "workspace")
REF = os.path.join(WS, "reference.wav")

SR = 24000

PHRASES = [
    "¿Qué tal mi juego? ¿Me escuchas bien?",
    "Hola amigo, me da mucho gusto verte, brother",
]

VARIANTS = [
    ("текущий (нейтральный)", dict(temperature=0.70, top_p=0.85, top_k=50, speed=1.0)),
    ("живее", dict(temperature=0.85, top_p=0.92, top_k=70, speed=1.03)),
    ("очень живо", dict(temperature=0.95, top_p=0.96, top_k=90, speed=1.05)),
    ("живее + разбивка", dict(temperature=0.85, top_p=0.92, top_k=70, speed=1.03,
                               enable_text_splitting=True)),
    ("текущий + разбивка", dict(temperature=0.70, top_p=0.85, top_k=50, speed=1.0,
                                 enable_text_splitting=True)),
    ("с длинным текстом", dict(temperature=0.85, top_p=0.92, top_k=70, speed=1.03,
                               length_penalty=1.2)),
    # repetition_penalty по умолчанию 10.0 — он ОЧЕНЬ консервативен и
    # выливает интонацию. Проверяем мягкие значения.
    ("мягкий штраф повтора", dict(temperature=0.75, top_p=0.88, top_k=55,
                                  speed=1.0, repetition_penalty=5.0)),
    ("живее + мягкий штраф", dict(temperature=0.88, top_p=0.93, top_k=75,
                                  speed=1.04, repetition_penalty=3.0)),
]


def load_model():
    from TTS.tts.configs.xtts_config import XttsConfig
    from TTS.tts.models.xtts import Xtts

    try:
        import xtts_clone
        xtts_clone.patch_torchaudio()
    except Exception:
        pass

    hf = os.path.expanduser(r"~\.cache\huggingface\hub")
    snaps = glob.glob(os.path.join(hf, "models--tts-hub--XTTS-v2", "snapshots", "*"))
    cfg = XttsConfig()
    cfg.load_json(os.path.join(snaps[0], "config.json"))
    tts = Xtts.init_from_config(cfg)
    tts.load_checkpoint(cfg, checkpoint_dir=snaps[0],
                        vocab_path=os.path.join(snaps[0], "vocab.json"))
    tts.cuda()
    return tts


def main() -> None:
    if not os.path.exists(REF):
        print(f"нет референса: {REF}")
        return
    tts = load_model()
    print("модель загружена", flush=True)
    gpt_latent, spk_emb = tts.get_conditioning_latents(audio_path=[REF])

    from faster_whisper import WhisperModel
    asr = WhisperModel("Systran/faster-whisper-small", device="cuda",
                       compute_type="float16")

    print("\n=== просодия и разборчивость по вариантам ===")
    for text in PHRASES:
        print(f"\n  ФРАЗА: {text!r}")
        print(f"    {'вариант':<26}{'сек':>6}{'F0 σ':>8}{'размах':>8}"
              f"{'понято':>10}")
        for name, params in VARIANTS:
            t0 = time.time()
            try:
                chunks = tts.inference_stream(
                    text, "es", gpt_latent, spk_emb,
                    stream_chunk_size=10, **params)
                audio = np.concatenate([c.detach().cpu().numpy() for c in chunks])
            except Exception as exc:
                print(f"    {name:<26} ОШИБКА {exc}")
                continue
            gen_ms = (time.time() - t0) * 1000
            dur = len(audio) / SR
            f0_std = prosody.f0_spread(audio, SR)
            f0_range = prosody.f0_range(audio, SR)
            # разборчивость: узнаём ли мы то, что синтезировали
            segs, _ = asr.transcribe(audio, language="es", beam_size=1,
                                     vad_filter=False,
                                     condition_on_previous_text=False)
            heard = " ".join(s.text.strip() for s in segs).strip()
            words_ok = len(set(heard.lower().split()) & set(text.lower().split()))
            total = len(set(text.lower().split()))
            score = words_ok / max(1, total)
            print(f"    {name:<26}{dur:>6.2f}{f0_std:>8.1f}{f0_range:>8.0f}"
                  f"{score:>9.0%}  ({gen_ms:.0f} мс)")
            print(f"      услышано: {heard[:70]!r}")


if __name__ == "__main__":
    main()
