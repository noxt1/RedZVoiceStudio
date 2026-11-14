"""Замер: размер чанка XTTS -> как быстро появляется первый звук.

При загруженной GPU (игра) важно не «скорость озвучки», а КОГДА появится
первый кусочек аудио. Мелкий чанк -> первый звук раньше, даже если вся
фраза будет готова позже.

Меряет первый звук и полный RTF для размеров чанка 5/10/20/40.

    "<engine>\\Scripts\\python.exe" research\\bench_chunk.py
"""

from __future__ import annotations

import os
import sys
import time

import numpy as np

WS = os.path.join(os.environ.get("LOCALAPPDATA", ""), "RedZVoiceStudio", "workspace")
HF = os.path.expanduser(r"~\.cache\huggingface\hub")
REF = os.path.join(WS, "reference.wav")

TEXT = ("Que chido, guay! Neta que no manches, a huevo, orale carnal, "
        "ya nos vamos, todo bien aqui en la casa.")


def main() -> None:
    import torch
    from TTS.tts.configs.xtts_config import XttsConfig
    from TTS.tts.models.xtts import Xtts

    sys.path.insert(0, os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
    import xtts_clone
    xtts_clone.patch_torchaudio()

    snap = glob_snap()
    cfg = XttsConfig()
    cfg.load_json(os.path.join(snap, "config.json"))
    model = Xtts.init_from_config(cfg)
    model.load_checkpoint(cfg, checkpoint_dir=snap,
                          vocab_path=os.path.join(snap, "vocab.json"))
    model.cuda()
    gpt_latent, spk_emb = model.get_conditioning_latents(audio_path=[REF])

    print(f"{'чанк':>7}{'первый звук':>14}{'всего аудио':>14}{'время':>10}{'RTF':>8}")
    for chunk in (5, 10, 20, 40):
        # прогрев
        for c in model.inference_stream(TEXT, "es", gpt_latent, spk_emb,
                                        stream_chunk_size=chunk, temperature=0.7):
            pass
        torch.cuda.synchronize()
        t0 = time.time()
        first = None
        total = 0
        for c in model.inference_stream(TEXT, "es", gpt_latent, spk_emb,
                                        stream_chunk_size=chunk, temperature=0.7):
            arr = c.detach().cpu().numpy()
            if first is None:
                first = time.time() - t0
            total += arr.shape[-1]
        elapsed = time.time() - t0
        audio_s = total / 24000
        print(f"{chunk:>7}{first * 1000:>12.0f} мс{audio_s:>13.2f} с"
              f"{elapsed:>9.2f} с{elapsed / audio_s:>8.3f}")

    print("\nМелкий чанк -> первый звук раньше (важно, когда GPU занят игрой).")


def glob_snap() -> str:
    import glob
    hits = glob.glob(os.path.join(HF, "models--tts-hub--XTTS-v2", "snapshots", "*"))
    return hits[0]


if __name__ == "__main__":
    main()
