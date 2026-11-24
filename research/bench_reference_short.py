"""Замер: какой референс даёт стабильный синтез КОРОТКИХ фраз.

Находка: XTTS надёжен на длинных фразах (2/2) и нестабилен на коротких
(2/5). Размер чанка и температура не помогают.

Гипотеза: дело в референсе. XTTS conditioning рассчитан на ~6 с «подсказки»
голоса, а reference.wav — это 24 с. Короткий образец (3–4 с) может
задать стиль чётче, и короткие фразы станут стабильными.

    "<engine>\\Scripts\\python.exe" research\\bench_reference_short.py
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
SAMPLES = os.path.join(WS, "voice_samples")

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


def words(text: str) -> set:
    text = re.sub(r"[¿?¡!.,]", " ", text.lower())
    return {w for w in text.split() if len(w) > 2}


def main() -> None:
    from faster_whisper import WhisperModel
    tts = load_model()
    asr = WhisperModel("Systran/faster-whisper-small", device="cuda",
                       compute_type="float16")
    print("модель загружена\n", flush=True)

    cands = [("reference.wav (24 с)", REF)]
    for name in ("take_02.wav", "take_04.wav", "take_05.wav", "take_07.wav"):
        p = os.path.join(SAMPLES, name)
        if os.path.exists(p):
            cands.append((name, p))

    for label, path in cands:
        gpt_latent, spk_emb = tts.get_conditioning_latents(audio_path=[path])
        ok_first = 0
        ok_any = 0
        spreads = []
        for text in SHORT:
            good = False
            for attempt in range(3):
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
                score = len(words(text) & words(heard)) / max(1, len(words(text)))
                if attempt == 0 and score >= 0.6:
                    ok_first += 1
                    good = True
                    spreads.append(prosody.f0_spread(audio, 24000))
                    break
                if score >= 0.6:
                    good = True
                    if not spreads:
                        spreads.append(prosody.f0_spread(audio, 24000))
            if good:
                ok_any += 1
        print(f"  {label:<22} с первой попытки {ok_first}/{len(SHORT)}  "
              f"за 3 попытки {ok_any}/{len(SHORT)}  "
              f"F0 σ={np.mean(spreads) if spreads else 0:.1f}")


if __name__ == "__main__":
    main()
