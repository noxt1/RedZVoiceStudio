"""Замер: даёт ли пост-обработка (интонация, паузы) ЖИВУЮ речь.

Сравниваем «сырой» синтез и обработанный:
  * разброс высоты (F0 σ) и размах — интонация;
  * разборчивость (Whisper) — не должна пострадать;
  * длительность.

    "<engine>\\Scripts\\python.exe" research\\bench_voice_post.py
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

# (русский, испанский, тон)
CASES = [
    ("Как вам моя игра? Вы ссаны ублюдки!", "¿Qué tal mi juego?",
     "aggressive"),
    ("Как твои дела, мой амиго?", "¿Cómo estás, amigo?", "friendly"),
    ("Что ты там делаешь?", "¿Qué estás haciendo ahí?", "neutral"),
    ("Ну всё, погнали работать", "Bueno, vamos a trabajar", "neutral"),
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

    print(f"  {'случай':<9}{'вариант':<10}{'сек':>6}{'F0 σ':>8}{'размах':>8}"
          f"{'понято':>9}")
    for ru, es, tone in CASES:
        params = voice_tone.params_for_tone(tone)
        spoken = voice_tone.apply_punctuation(es, tone)
        import torch
        torch.manual_seed(1234)
        chunks = tts.inference_stream(spoken, "es", gpt_latent, spk_emb,
                                      stream_chunk_size=10, **params)
        raw = np.concatenate([c.detach().cpu().numpy() for c in chunks]
                              ).astype(np.float32)
        for label, audio in (("сырой", raw),
                              ("с интон.", voice_post.add_life(raw, SR, tone,
                                                             spoken))):
            segs, _ = asr.transcribe(audio, language="es", beam_size=1,
                                     vad_filter=False,
                                     condition_on_previous_text=False)
            heard = " ".join(s.text.strip() for s in segs).strip()
            import re
            want = {w for w in re.split(r"\s+", es.lower().replace("¿", "")
                                        .replace("?", " ").strip())
                    if len(w) > 2}
            got = {w for w in re.split(r"\s+", heard.lower().replace("¿", "")
                                      .replace("?", " ").strip()) if len(w) > 2}
            score = len(want & got) / max(1, len(want))
            print(f"  {tone:<9}{label:<10}{len(audio)/SR:>6.2f}"
                  f"{prosody.f0_spread(audio, SR):>8.1f}"
                  f"{prosody.f0_range(audio, SR):>8.0f}{score:>9.0%}")
        print()


if __name__ == "__main__":
    main()
