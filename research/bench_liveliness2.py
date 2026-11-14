"""Замер: откуда берётся «живость» голоса.

Гипотеза: XTTS копирует ПРОСОДИЮ референса. Если референс записан
монотонно (24 с чтения вслух), клон тоже будет читать с листа.

Проверяем:
  * какой референс даёт более живую подачу (разные образцы + эталон);
  * влияет ли разбивка текста на фразы (enable_text_splitting).

    "<engine>\\Scripts\\python.exe" research\\bench_liveliness2.py
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
SAMPLES = os.path.join(WS, "voice_samples")

SR = 24000
TEXT = "¿Qué tal mi juego? ¿Me escuchas bien? ¡VIVA MÉXICO!"

# параметры: умеренная температура (выше 0.9 — каша), без length_penalty
BASE = dict(temperature=0.75, top_p=0.88, top_k=60, speed=1.02)


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
    import soundfile as sf
    from faster_whisper import WhisperModel

    tts = load_model()
    asr = WhisperModel("Systran/faster-whisper-small", device="cuda",
                       compute_type="float16")
    print("модель загружена", flush=True)

    # кандидаты-референсы: эталон + самые выразительные образцы
    cands = [("reference.wav (эталон)", REF)]
    for name in ("take_04.wav", "take_02.wav", "take_07.wav", "take_05.wav"):
        p = os.path.join(SAMPLES, name)
        if os.path.exists(p):
            cands.append((name, p))

    print(f"\n  {'референс':<24}{'сплит':>7}{'сек':>7}{'F0 σ':>8}{'размах':>8}"
          f"{'понято':>9}")
    for label, path in cands:
        try:
            gpt_latent, spk_emb = tts.get_conditioning_latents(audio_path=[path])
        except Exception as exc:
            print(f"  {label:<24} ОШИБКА {exc}")
            continue
        # просодия самого референса (для сравнения)
        try:
            a, sr = sf.read(path, dtype="float32", always_2d=False)
            if a.ndim > 1:
                a = a.mean(axis=1)
            r_std = prosody.f0_spread(a, sr)
            r_rng = prosody.f0_range(a, sr)
        except Exception:
            r_std = r_rng = 0.0
        for split in (False, True):
            params = dict(BASE)
            if split:
                params["enable_text_splitting"] = True
            t0 = time.time()
            try:
                chunks = tts.inference_stream(
                    TEXT, "es", gpt_latent, spk_emb,
                    stream_chunk_size=10, **params)
                audio = np.concatenate([c.detach().cpu().numpy() for c in chunks])
            except Exception as exc:
                print(f"  {label:<24} {str(split):>7}  ОШИБКА {exc}")
                continue
            gen_ms = (time.time() - t0) * 1000
            dur = len(audio) / SR
            f0_std = prosody.f0_spread(audio, SR)
            f0_rng = prosody.f0_range(audio, SR)
            segs, _ = asr.transcribe(audio, language="es", beam_size=1,
                                     vad_filter=False,
                                     condition_on_previous_text=False)
            heard = " ".join(s.text.strip() for s in segs).strip().lower()
            want = set(TEXT.lower().replace("!", "").replace("¿", "")
                       .replace("?", "").split())
            got = set(heard.replace("!", "").replace("¿", "")
                      .replace("?", "").split())
            score = len(want & got) / max(1, len(want))
            print(f"  {label:<24}{str(split):>7}{dur:>7.2f}{f0_std:>8.1f}"
                  f"{f0_rng:>8.0f}{score:>9.0%}  "
                  f"(реф: σ={r_std:.0f} размах={r_rng:.0f}, {gen_ms:.0f} мс)")


if __name__ == "__main__":
    main()
