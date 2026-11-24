"""КЛЮЧЕВОЙ ЗАМЕР: задержка стримингового XTTS-v2 (клонирование голоса).

Цель: понять, реально ли «говоришь по-русски -> слышат на испанском вживую».

Меряем:
  * время до первого чанка аудио (это то, что слышат люди)
  * полный RTF (real-time factor) потокового режима
  * сравнение с обычным (не потоковым) inference

Запуск (нужен движок с torch/coqui-tts):
    "C:\\Users\\cyril\\AppData\\Local\\Auraloom\\engine\\Scripts\\python.exe" research\\bench_xtts_stream.py
"""

from __future__ import annotations

import glob
import os
import sys
import time

import numpy as np

WS = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Auraloom", "workspace")
REF = os.path.join(WS, "reference.wav")
HF = os.path.expanduser(r"~\.cache\huggingface\hub\models--tts-hub--XTTS-v2")
SNAP = glob.glob(os.path.join(HF, "snapshots", "*"))
SNAP = SNAP[0] if SNAP else None

TEXT_ES = "No manches, carnal, ya casi terminamos el trabajo, vamos!"
TEXT_LONG = ("Que chido, guay! Neta que no manches, a huevo, orale carnal, "
             "ya nos vamos, todo bien aqui en la casa.")


def load_model():
    from TTS.tts.configs.xtts_config import XttsConfig
    from TTS.tts.models.xtts import Xtts

    # torchcodec требует системный FFmpeg -> подменяем torchaudio на soundfile
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "..", "tools"))
        import xtts_clone
        xtts_clone.patch_torchaudio()
        print("torchaudio подменён на soundfile (обход torchcodec)")
    except Exception as exc:
        print(f"не удалось применить патч torchaudio: {exc}")

    t0 = time.time()
    config = XttsConfig()
    config.load_json(os.path.join(SNAP, "config.json"))
    model = Xtts.init_from_config(config)
    model.load_checkpoint(config, checkpoint_dir=SNAP, vocab_path=os.path.join(SNAP, "vocab.json"))
    model.cuda()
    print(f"модель загружена за {time.time() - t0:.1f} с")
    return model


def bench_stream(model, text: str, label: str, chunk: int = 20) -> dict:
    import torch

    t0 = time.time()
    gpt_cond_latent, speaker_embedding = model.get_conditioning_latents(
        audio_path=[REF])
    cond_time = time.time() - t0
    print(f"conditioning latents (кэш голоса): {cond_time:.2f} с")

    t0 = time.time()
    chunks = model.inference_stream(
        text, "es", gpt_cond_latent, speaker_embedding,
        stream_chunk_size=chunk, temperature=0.7)
    first = None
    total_samples = 0
    n = 0
    for i, c in enumerate(chunks):
        arr = c.detach().cpu().numpy() if hasattr(c, "detach") else np.asarray(c)
        if first is None:
            first = time.time() - t0
            print(f"  [{label}] ПЕРВЫЙ ЗВУК через {first * 1000:.0f} мс "
                  f"({arr.shape[-1] / 24000:.3f} с аудио)")
        total_samples += arr.shape[-1]
        n += 1
    elapsed = time.time() - t0
    audio_s = total_samples / 24000
    rtf = elapsed / audio_s if audio_s else 0
    print(f"  [{label}] ИТОГО: {audio_s:.2f} с аудио за {elapsed:.2f} с "
          f"(RTF {rtf:.3f}), чанков {n}")
    return {"first": first, "rtf": rtf, "audio": audio_s, "elapsed": elapsed,
            "chunks": n, "cond": cond_time}


def bench_plain(model, text: str, label: str) -> dict:
    t0 = time.time()
    gpt_cond_latent, speaker_embedding = model.get_conditioning_latents(
        audio_path=[REF])
    cond_time = time.time() - t0
    t0 = time.time()
    out = model.inference(text, "es", gpt_cond_latent, speaker_embedding,
                          temperature=0.7)
    elapsed = time.time() - t0
    wav = np.asarray(out["wav"], dtype=np.float32)
    audio_s = len(wav) / 24000
    print(f"  [{label}] обычный inference: {audio_s:.2f} с аудио за {elapsed:.2f} с "
          f"(RTF {elapsed / audio_s:.3f}), conditioning {cond_time:.2f} с")
    return {"total": elapsed + cond_time, "rtf": elapsed / audio_s}


def main() -> None:
    if not SNAP or not os.path.exists(REF):
        sys.exit("нет модели XTTS или reference.wav")
    print(f"модель: {SNAP}")
    print(f"образец: {REF}\n")

    model = load_model()

    print("\n=== 1. ПОТОКОВЫЙ РЕЖИМ (то, что нужно для «вживую») ===")
    s1 = bench_stream(model, TEXT_ES, "короткая")
    s2 = bench_stream(model, TEXT_LONG, "длинная")

    print("\n=== 2. ОБЫЧНЫЙ РЕЖИМ (для сравнения) ===")
    p1 = bench_plain(model, TEXT_ES, "короткая")

    print("\n=== ИТОГИ ===")
    print(f"  до первого звука (короткая фраза): {s1['first'] * 1000:.0f} мс")
    print(f"  до первого звука (длинная фраза):  {s2['first'] * 1000:.0f} мс")
    print(f"  RTF потоковый: {s1['rtf']:.3f} / {s2['rtf']:.3f}")
    print(f"  RTF обычный:    {p1['rtf']:.3f}")
    print("\n  Вывод: если до первого звука < 500 мс — «вживую» возможно.")


if __name__ == "__main__":
    main()
