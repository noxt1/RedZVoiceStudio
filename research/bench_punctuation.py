"""Замер: влияет ли знак препинания на интонацию XTTS.

Гипотеза: эмоцию в синтезе несёт ПУНКТУАЦИЯ. Перевод (opus-mt) почти
никогда не ставит «!» — поэтому злая фраза звучит как чтение с листа.
Если добавить «¡...!» по тону русского текста, интонация должна
остаться словами, но стать живой.

    "<engine>\\Scripts\\python.exe" research\\bench_punctuation.py
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

BASE = dict(temperature=0.75, top_p=0.88, top_k=60, speed=1.02,
           repetition_penalty=5.0)

CASES = [
    ("обычная (без знаков)", "¿Qué tal mi juego? ¿Me escuchas bien?",
     "¿Qué tal mi juego? ¿Me escuchas bien?"),
    ("с восклицанием", "¿Qué tal mi juego? ¿Me escuchas bien?",
     "¡¿Qué tal mi juego! ¿Me escuchas bien!?"),
    ("злая — обычная", "Eres un maldito cabron, no me jodas",
     "Eres un maldito cabron, no me jodas"),
    ("злая — с восклицанием", "Eres un maldito cabron, no me jodas",
     "¡Eres un maldito cabron, no me jodas!"),
    ("дружеская — обычная", "Hola amigo, me da mucho gusto verte",
     "Hola amigo, me da mucho gusto verte"),
    ("дружеская — с восклицанием", "Hola amigo, me da mucho gusto verte",
     "¡Hola amigo, me da mucho gusto verte!"),
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
    from faster_whisper import WhisperModel
    tts = load_model()
    asr = WhisperModel("Systran/faster-whisper-small", device="cuda",
                       compute_type="float16")
    gpt_latent, spk_emb = tts.get_conditioning_latents(audio_path=[REF])
    print("модель загружена\n", flush=True)

    print(f"  {'случай':<30}{'сек':>6}{'F0 σ':>8}{'размах':>8}{'понято':>9}")
    for label, _ru, text in CASES:
        t0 = time.time()
        chunks = tts.inference_stream(text, "es", gpt_latent, spk_emb,
                                      stream_chunk_size=10, **BASE)
        audio = np.concatenate([c.detach().cpu().numpy() for c in chunks])
        gen_ms = (time.time() - t0) * 1000
        dur = len(audio) / SR
        f0_std = prosody.f0_spread(audio, SR)
        f0_rng = prosody.f0_range(audio, SR)
        segs, _ = asr.transcribe(audio, language="es", beam_size=1,
                                 vad_filter=False,
                                 condition_on_previous_text=False)
        heard = " ".join(s.text.strip() for s in segs).strip()
        import re
        want = {w for w in re.split(r"\s+", text.lower()
                                    .replace("¡", "").replace("!",
                                                            "").replace("?", " ")
                                    .strip()) if len(w) > 2}
        got = {w for w in re.split(r"\s+", heard.lower().replace("¿", "")
                                  .replace("?", " ").replace("!", " ").strip())
               if len(w) > 2}
        score = len(want & got) / max(1, len(want))
        print(f"  {label:<30}{dur:>6.2f}{f0_std:>8.1f}{f0_rng:>8.0f}"
              f"{score:>9.0%}  ({gen_ms:.0f} мс)")
        print(f"      {heard[:60]!r}")


if __name__ == "__main__":
    main()
