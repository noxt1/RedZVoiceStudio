r"""Подбор устойчивых формулировок для XTTS.

Некоторые реплики XTTS произносит нестабильно ("Bajese!", "Arriba!").
Скрипт перебирает варианты и печатает, какие звучат надёжно.

    python tools\pick_phrasing.py --ref reference.wav
"""

from __future__ import annotations

import argparse
import os
import sys
import unicodedata

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)
os.environ.setdefault("COQUI_TOS_AGREED", "1")

from xtts_clone import norm, patch_torchaudio, similarity  # noqa: E402

# Кандидаты на замену проблемных реплик.
CANDIDATES = {
    "11": ["Arriba!", "¡Arriba!", "Sube!", "Arriba, arriba!"],
    "12": ["Abajo!", "¡Abajo!", "Bajese!", "Abajo, abajo!"],
    "17": ["¡Dispara primero!", "Dispare primero!", "Dispara primero!"],
    "19": ["¡Auxilio!", "Auxilio!", "Socorro!"],
    "23": ["Socorro por favor!", "¡Auxilio, por favor!", "Ayuda, por favor!"],
    "06": ["Que pedo, guay!", "¡Que pedo, guay!", "Que pedo, carnal!",
           "No pedo, guay!", "Que hueva, guay!"],
    "02": ["No manches, guay!", "¡No manches, guay!", "No manches, carnal!",
           "Neta, no manches!", "Que no manches, guay!"],
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ref", required=True)
    parser.add_argument("--attempts", type=int, default=5)
    args = parser.parse_args()

    patch_torchaudio()

    import torch
    from TTS.api import TTS
    from faster_whisper import WhisperModel

    model = TTS(model_name="tts_models/multilingual/multi-dataset/xtts_v2", progress_bar=False).to("cuda")
    whisper = WhisperModel("small", device="cpu", compute_type="int8")

    profiles = [
        {},
        {"temperature": 0.45, "top_p": 0.75, "top_k": 25},
        {"split_sentences": False},
        {"split_sentences": False, "temperature": 0.45, "top_p": 0.75, "top_k": 25},
        {"split_sentences": False, "temperature": 0.30, "top_p": 0.65, "top_k": 15},
    ]

    for lid, options in CANDIDATES.items():
        print(f"\n=== {lid}")
        for text in options:
            scores = []
            for attempt, profile in enumerate(profiles[:args.attempts]):
                torch.manual_seed(1234 + attempt * 977)
                kwargs = {"split_sentences": True}
                kwargs.update(profile)
                out = model.tts(text=text, speaker_wav=args.ref, language="es", **kwargs)
                audio = np.asarray(out, dtype="float32")
                if audio.ndim > 1:
                    audio = audio.mean(axis=1)
                audio = __import__("audio_post").to_16k(audio, 24000)
                segs, _ = whisper.transcribe(
                    audio, language="es", beam_size=1, vad_filter=False,
                    condition_on_previous_text=False,
                )
                heard = " ".join(s.text.strip() for s in segs).strip()
                scores.append((similarity(heard, text), heard))
            best = max(scores, key=lambda s: s[0])
            ok = sum(1 for s in scores if s[0] >= 0.999)
            mark = "STABLE " if ok >= 3 else "unstable"
            print(f"  {mark} ({ok}/{len(scores)} exact) {text!r} best={best[0]:.2f} heard={best[1][:32]!r}")


if __name__ == "__main__":
    main()
