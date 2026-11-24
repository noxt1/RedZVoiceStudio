"""A/B: старые параметры против новых (разбивка фраз + мягкий штраф повтора).

Меряем для каждой фразы:
  * разброс и размах высоты (интонация);
  * разборчивость (Whisper);
  * темп (длительность).

    "<engine>\\Scripts\\python.exe" research\\bench_ab_voice.py
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

WS = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Auraloom", "workspace")
REF = os.path.join(WS, "reference.wav")
SR = 24000

PHRASES = [
    ("обычная", "¿Qué tal mi juego? ¿Me escuchas bien?"),
    ("злая", "Eres un maldito cabron, no me jodas"),
    ("дружеская", "Hola amigo, me da mucho gusto verte"),
]

OLD = dict(temperature=0.70, top_p=0.85, top_k=50, speed=1.0)
NEW = dict(temperature=0.75, top_p=0.88, top_k=60, speed=1.02,
           repetition_penalty=5.0, enable_text_splitting=True)
NEW_HOT = dict(temperature=0.82, top_p=0.92, top_k=72, speed=1.06,
               repetition_penalty=4.0, enable_text_splitting=True)


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


def norm_words(text: str) -> set:
    import re
    text = text.lower().replace("¿", "").replace("?", "").replace("¡", "")
    text = text.replace("!", "").replace(".", "").replace(",", "")
    return {w for w in re.split(r"\s+", text) if len(w) > 2}


def main() -> None:
    from faster_whisper import WhisperModel
    tts = load_model()
    asr = WhisperModel("Systran/faster-whisper-small", device="cuda",
                       compute_type="float16")
    gpt_latent, spk_emb = tts.get_conditioning_latents(audio_path=[REF])
    print("модель загружена\n", flush=True)

    totals = {}
    for label, text in PHRASES:
        print(f"  ФРАЗА ({label}): {text!r}")
        for name, params in (("старые", OLD), ("новые", NEW), ("новые+живо", NEW_HOT)):
            t0 = time.time()
            chunks = tts.inference_stream(text, "es", gpt_latent, spk_emb,
                                          stream_chunk_size=10, **params)
            audio = np.concatenate([c.detach().cpu().numpy() for c in chunks])
            gen_ms = (time.time() - t0) * 1000
            dur = len(audio) / SR
            f0_std = prosody.f0_spread(audio, SR)
            f0_rng = prosody.f0_range(audio, SR)
            segs, _ = asr.transcribe(audio, language="es", beam_size=1,
                                     vad_filter=False,
                                     condition_on_previous_text=False)
            heard = " ".join(s.text.strip() for s in segs).strip()
            want = norm_words(text)
            got = norm_words(heard)
            score = len(want & got) / max(1, len(want))
            totals.setdefault(name, []).append((f0_std, f0_rng, score, dur))
            print(f"    {name:<12} сек={dur:.2f}  F0 σ={f0_std:5.1f}  "
                  f"размах={f0_rng:4.0f}  понятно={score:.0%}  "
                  f"({gen_ms:.0f} мс)")
            print(f"      услышано: {heard[:70]!r}")
        print()

    print("=== ИТОГ (среднее по фразам) ===")
    for name, rows in totals.items():
        a = np.array([[r[0], r[1], r[2] * 100, r[3]] for r in rows])
        print(f"  {name:<12} F0 σ={a[:,0].mean():5.1f}  размах={a[:,1].mean():4.0f}"
              f"  понятно={a[:,2].mean():3.0f}%  сек={a[:,3].mean():.2f}")


if __name__ == "__main__":
    main()
