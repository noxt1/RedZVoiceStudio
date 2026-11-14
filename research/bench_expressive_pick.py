"""Замер: насколько «плоский» синтез живого перевода и помогает ли перебор.

Сравниваем:
  * ОДИН вариант синтеза (как сейчас в живом переводе);
  * НЕСКОЛЬКО вариантов с разными seed и выбором самого выразительного
    (так же, как уже работает озвучка фраз: авто-починка по просодии).

Метрики: разброс высоты (F0 σ) — «живость», разборчивость, время.

    "<engine>\\Scripts\\python.exe" research\\bench_expressive_pick.py
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
import voice_tone  # noqa: E402

WS = os.path.join(os.environ.get("LOCALAPPDATA", ""), "RedZVoiceStudio", "workspace")
REF = os.path.join(WS, "reference.wav")
SR = 24000

PHRASES = [
    ("¿Qué tal mi juego? ¿Me escuchas bien?", "neutral"),
    ("Eres un maldito cabron, no me jodas", "aggressive"),
    ("Hola amigo, me da mucho gusto verte", "friendly"),
    ("Bueno, vamos a trabajar, que ya es tarde", "neutral"),
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

    print(f"  {'фраза':<34}{'вариант':<14}{'F0 σ':>7}{'размах':>8}"
          f"{'понято':>9}{'мс':>7}")
    for text, tone in PHRASES:
        params = voice_tone.params_for_tone(tone)
        spoken = voice_tone.apply_punctuation(text, tone)
        best = None
        for variant in ("один", "3 варианта"):
            t0 = time.time()
            if variant == "один":
                import torch
                torch.manual_seed(1234)
                chunks = tts.inference_stream(spoken, "es", gpt_latent, spk_emb,
                                              stream_chunk_size=10, **params)
                audio = np.concatenate([c.detach().cpu().numpy()
                                        for c in chunks]).astype(np.float32)
            else:
                best_audio, best_std = None, -1.0
                for attempt in range(3):
                    import torch
                    torch.manual_seed(1234 + attempt * 7919)
                    chunks = tts.inference_stream(spoken, "es", gpt_latent,
                                                  spk_emb, stream_chunk_size=10,
                                                  **params)
                    cand = np.concatenate([c.detach().cpu().numpy()
                                           for c in chunks]).astype(np.float32)
                    std = prosody.f0_spread(cand, SR)
                    if std > best_std:
                        best_std, best_audio = std, cand
                audio = best_audio
            gen_ms = (time.time() - t0) * 1000
            segs, _ = asr.transcribe(audio, language="es", beam_size=1,
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
            print(f"  {text[:32]:<34}{variant:<14}"
                  f"{prosody.f0_spread(audio, SR):>7.1f}"
                  f"{prosody.f0_range(audio, SR):>8.0f}{score:>9.0%}"
                  f"{gen_ms:>7.0f}")
        print()


if __name__ == "__main__":
    main()
