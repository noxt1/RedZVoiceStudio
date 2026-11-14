"""Замер: помогает ли сильный интонационный контур (без повторного синтеза).

Плоский синтез (размах высоты 48 Гц) — это и есть «монотонное чтение».
Вариант «3 варианта» даёт размах 156 Гц, но стоит тройного времени синтеза.

Проверяем: хватит ли ЛЁГКОГО контура высоты (пересемплирование), чтобы
фраза перестала звучать плоской — и не пострадала ли разборчивость.

    "<engine>\\Scripts\\python.exe" research\\bench_contour.py
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
import voice_post  # noqa: E402
import voice_tone  # noqa: E402

WS = os.path.join(os.environ.get("LOCALAPPDATA", ""), "RedZVoiceStudio", "workspace")
REF = os.path.join(WS, "reference.wav")
SR = 24000

PHRASES = [
    ("Hola amigo, me da mucho gusto verte", "friendly"),
    ("Bueno, vamos a trabajar, que ya es tarde", "neutral"),
    ("¿Qué tal mi juego? ¿Me escuchas bien?", "neutral"),
    ("Eres un maldito cabron, no me jodas", "aggressive"),
]

DEPTHS = (0.0, 0.06, 0.10, 0.14)


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

    for text, tone in PHRASES:
        params = voice_tone.params_for_tone(tone)
        spoken = voice_tone.apply_punctuation(text, tone)
        import torch
        torch.manual_seed(1234)
        chunks = tts.inference_stream(spoken, "es", gpt_latent, spk_emb,
                                      stream_chunk_size=10, **params)
        raw = np.concatenate([c.detach().cpu().numpy() for c in chunks]
                             ).astype(np.float32)
        print(f"  {text!r}")
        for depth in DEPTHS:
            t0 = time.time()
            out = voice_post.add_life(raw, SR, tone, spoken, depth=depth)
            ms = (time.time() - t0) * 1000
            segs, _ = asr.transcribe(out, language="es", beam_size=1,
                                     vad_filter=False,
                                     condition_on_previous_text=False)
            heard = " ".join(s.text.strip() for s in segs).strip()
            import re
            want = {w for w in re.split(r"\s+", text.lower().replace("¿", "")
                                        .replace("?", " ").strip())
                    if len(w) > 2}
            got = {w for w in re.split(r"\s+", heard.lower().replace("¿", "")
                                      .replace("?", " ").strip()) if len(w) > 2}
            score = len(want & got) / max(1, len(want))
            print(f"      глубина {depth:.2f}: F0 σ={prosody.f0_spread(out, SR):5.1f}"
                  f"  размах={prosody.f0_range(out, SR):4.0f}"
                  f"  понятно={score:4.0%}  ({ms:4.0f} мс, {len(out)/SR:.2f}с)")
        print()


if __name__ == "__main__":
    main()
