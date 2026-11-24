"""Диагностика: что именно ломается на коротких фразах.

Печатаем, что реально получилось, и пробуем несколько seed'ов — так видно,
это порча слов или просто оценка слишком строгая.

    "<engine>\\Scripts\\python.exe" research\\diag_short.py
"""

from __future__ import annotations

import glob
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

WS = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Auraloom", "workspace")
REF = os.path.join(WS, "reference.wav")

SHORT = [
    "¿Qué tal mi juego?",
    "¿Oyen el ruso o no?",
    "Eso es todo",
    "Ven aquí",
    "No me jodas",
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

    for text in SHORT:
        print(f"  {text!r}")
        for attempt in range(4):
            import torch
            torch.manual_seed(1234 + attempt * 7919)
            chunks = tts.inference_stream(
                text, "es", gpt_latent, spk_emb,
                stream_chunk_size=10, temperature=0.75, top_p=0.88,
                top_k=60, speed=1.02, repetition_penalty=5.0)
            audio = np.concatenate([c.detach().cpu().numpy() for c in chunks])
            segs, _ = asr.transcribe(audio, language="es", beam_size=1,
                                     vad_filter=False,
                                     condition_on_previous_text=False)
            heard = " ".join(s.text.strip() for s in segs).strip()
            print(f"      seed{attempt}: {heard!r}  ({len(audio)/24000:.2f} с)")
        print()


if __name__ == "__main__":
    main()
