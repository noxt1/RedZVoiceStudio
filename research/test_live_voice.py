"""Проверка «живости» на реальных фразах: тон -> параметры -> звук.

Берём реальные фразы пользователя (из журнала движка), прогоняем через
движок и проверяем:
  * тон определился по РУССКОМУ тексту;
  * разборчивость не пострадала (Whisper узнаёт слова);
  * интонация не «плоская» (разброс высоты выше, чем у ровного чтения).

    "<engine>\\Scripts\\python.exe" research\\test_live_voice.py
"""

from __future__ import annotations

import glob
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import live_translate as lt  # noqa: E402
import prosody  # noqa: E402
import voice_tone as vt  # noqa: E402

WS = os.path.join(os.environ.get("LOCALAPPDATA", ""), "RedZVoiceStudio", "workspace")
REF = os.path.join(WS, "reference.wav")
SR = 24000

# (русский как сказал игрок, испанский перевод)
CASES = [
    ("Как вам моя игра? Вы ссаны ублюдки!", "¿Qué tal mi juego?"),
    ("Где эти сраные мексиканцы?", "¿Dónde están esos malditos mexicanos?"),
    ("Как твои дела, мой амиго?", "¿Cómo estás, amigo?"),
    ("Что ты там делаешь?", "¿Qué estás haciendo ahí?"),
    ("Русский слышен или нет?", "¿Oyen el ruso o no?"),
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

    print(f"  {'тон':<11}{'F0 σ':>8}{'размах':>8}{'понято':>9}  текст")
    for ru, es in CASES:
        tone, params = lt._tone_params(es, ru, 2)
        spoken = vt.apply_punctuation(es, tone)
        t0 = time.time()
        chunks = tts.inference_stream(spoken, "es", gpt_latent, spk_emb,
                                      stream_chunk_size=10, **params)
        audio = np.concatenate([c.detach().cpu().numpy() for c in chunks])
        gen_ms = (time.time() - t0) * 1000
        segs, _ = asr.transcribe(audio, language="es", beam_size=1,
                                 vad_filter=False,
                                 condition_on_previous_text=False)
        heard = " ".join(s.text.strip() for s in segs).strip()
        import re
        want = {w for w in re.split(r"\s+", es.lower().replace("¿", "")
                                    .replace("?", " ").strip()) if len(w) > 2}
        got = {w for w in re.split(r"\s+", heard.lower().replace("¿", "")
                                  .replace("?", " ").strip()) if len(w) > 2}
        score = len(want & got) / max(1, len(want))
        f0_std = prosody.f0_spread(audio, SR)
        f0_rng = prosody.f0_range(audio, SR)
        print(f"  {tone:<11}{f0_std:>8.1f}{f0_rng:>8.0f}{score:>9.0%}  "
              f"{spoken!r}")
        print(f"      услышано: {heard[:60]!r}  ({gen_ms:.0f} мс)")


if __name__ == "__main__":
    main()
