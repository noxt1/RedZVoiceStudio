"""Замер: размер чанка и надёжность коротких фраз.

Короткие фразы ломаются при ЛЮБОЙ температуре (2/5), длинные — всегда.
Значит дело не в сэмплировании, а в том, сколько текста XTTS видит за раз.

stream_chunk_size — сколько токенов аудио отдаётся за шаг. Мелкие чанки
(10) означают, что модель «думает» кусками и короткая фраза рвётся.

Проверяем размер чанка и «подложку» из естественного вступления.

    "<engine>\\Scripts\\python.exe" research\\bench_chunk_liveliness.py
"""

from __future__ import annotations

import glob
import os
import re
import sys

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

VARIANTS = [
    ("чанк 10 (сейчас)", dict(stream_chunk_size=10)),
    ("чанк 20", dict(stream_chunk_size=20)),
    ("чанк 40", dict(stream_chunk_size=40)),
    ("чанк 80", dict(stream_chunk_size=80)),
    ("чанк 40 + вступление", dict(stream_chunk_size=40)),
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

    for name, extra in VARIANTS:
        ok = 0
        spreads = []
        for text in SHORT:
            spoken = text
            if "вступление" in name:
                spoken = "Bueno, " + text
            import torch
            torch.manual_seed(1234)
            chunks = tts.inference_stream(
                spoken, "es", gpt_latent, spk_emb,
                temperature=0.75, top_p=0.88, top_k=60, speed=1.02,
                repetition_penalty=5.0, **extra)
            audio = np.concatenate([c.detach().cpu().numpy() for c in chunks])
            segs, _ = asr.transcribe(audio, language="es", beam_size=1,
                                     vad_filter=False,
                                     condition_on_previous_text=False)
            heard = " ".join(s.text.strip() for s in segs).strip()
            score = len(words(text) & words(heard)) / max(1, len(words(text)))
            if score >= 0.6:
                ok += 1
                spreads.append(prosody.f0_spread(audio, SR))
        print(f"  {name:<24} понятно {ok}/{len(SHORT)}  "
              f"F0 σ={np.mean(spreads) if spreads else 0:.1f}")


if __name__ == "__main__":
    main()
