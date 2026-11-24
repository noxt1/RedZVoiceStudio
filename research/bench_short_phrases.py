"""Замер: короткие фразы и температура сэмплирования.

Проблема: жив��й перевод произносит КОРОТКИЕ фразы («¿Qué tal mi juego?»),
а XTTS на коротком тексте нестабилен — то читает ровно, то выдаёт мусор
(«¡Titan Michuevo!»).

Проверяем: как часто фраза ломается на разных температурах и длинах.

    "<engine>\\Scripts\\python.exe" research\\bench_short_phrases.py
"""

from __future__ import annotations

import glob
import os
import re
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import prosody  # noqa: E402

WS = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Auraloom", "workspace")
REF = os.path.join(WS, "reference.wav")
SR = 24000

SHORT = [
    "¿Qué tal mi juego?",
    "¿Oyen el ruso o no?",
    "Eso es todo",
    "Ven aquí",
    "No me jodas",
]
LONG = [
    "¿Qué tal mi juego? ¿Me escuchas bien?",
    "Hola amigo, me da mucho gusto verte, ¿cómo estás?",
]
TEMPS = [0.60, 0.70, 0.75, 0.82]


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


def words(text: str) -> set:
    text = re.sub(r"[¿?¡!.,]", " ", text.lower())
    return {w for w in text.split() if len(w) > 2}


def main() -> None:
    from faster_whisper import WhisperModel
    tts = load_model()
    asr = WhisperModel("Systran/faster-whisper-small", device="cuda",
                       compute_type="float16")
    gpt_latent, spk_emb = tts.get_conditioning_latents(audio_path=[REF])
    print("модель загружена\n", flush=True)

    for label, phrases in (("КОРОТКИЕ", SHORT), ("ДЛИННЫЕ", LONG)):
        print(f"  === {label} фразы ===")
        for temp in TEMPS:
            ok_count = 0
            spreads = []
            for text in phrases:
                for attempt in range(2):     # два seed'а на фразу
                    import torch
                    torch.manual_seed(1000 + attempt * 7919)
                    chunks = tts.inference_stream(
                        text, "es", gpt_latent, spk_emb,
                        stream_chunk_size=10, temperature=temp,
                        top_p=0.88, top_k=60, speed=1.02,
                        repetition_penalty=5.0)
                    audio = np.concatenate([c.detach().cpu().numpy()
                                            for c in chunks])
                    segs, _ = asr.transcribe(audio, language="es", beam_size=1,
                                             vad_filter=False,
                                             condition_on_previous_text=False)
                    heard = " ".join(s.text.strip() for s in segs).strip()
                    w, g = words(text), words(heard)
                    score = len(w & g) / max(1, len(w))
                    if score >= 0.6:
                        ok_count += 1
                        spreads.append(prosody.f0_spread(audio, SR))
                        break
            print(f"    temp={temp:.2f}  понято с первой попытки/двух: "
                  f"{ok_count}/{len(phrases)}  F0 σ={np.mean(spreads):.1f}")


if __name__ == "__main__":
    main()
