"""Диагностика XTTS: как влияют параметры сэмплирования и split_sentences.

Используется для выбора рабочих настроек в xtts_clone.py.

    python tools/diagnose_xtts.py --reference ref.wav
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", required=True)
    parser.add_argument("--cases", default="04,23,29")
    args = parser.parse_args()

    patch_torchaudio()

    import json
    from TTS.api import TTS
    from faster_whisper import WhisperModel

    with open(os.path.join(ROOT, "lines.json"), encoding="utf-8") as fh:
        lines = {l["id"]: l for l in json.load(fh)["lines"]}

    model = TTS(model_name="tts_models/multilingual/multi-dataset/xtts_v2", progress_bar=False).to("cuda")
    whisper = WhisperModel("small", device="cpu", compute_type="int8")

    profiles = [
        ("base", {}, True),
        ("base-nosplit", {}, False),
        ("cool", {"temperature": 0.45, "top_p": 0.75, "top_k": 25}, True),
        ("cool-nosplit", {"temperature": 0.45, "top_p": 0.75, "top_k": 25}, False),
        ("cold", {"temperature": 0.30, "top_p": 0.65, "top_k": 15, "repetition_penalty": 8.0}, False),
        ("slow", {"temperature": 0.45, "top_p": 0.75, "top_k": 25, "speed": 0.92}, False),
    ]

    ids = [c.strip() for c in args.cases.split(",") if c.strip()]
    for lid in ids:
        expected = lines[lid]["es"]
        print(f"\n--- {lid}: {expected}")
        for label, profile, split in profiles:
            out = model.tts(
                text=expected,
                speaker_wav=args.reference,
                language="es",
                split_sentences=split,
                **profile,
            )
            audio = np.asarray(out, dtype="float32")
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            audio = __import__("audio_post").to_16k(audio, 24000)
            segs, _ = whisper.transcribe(
                audio, language="es", beam_size=1, vad_filter=False,
                condition_on_previous_text=False,
            )
            heard = " ".join(s.text.strip() for s in segs).strip()
            score = similarity(heard, expected)
            mark = "OK " if score >= 0.999 else ("~  " if score >= 0.85 else "BAD")
            print(f"  {mark} {label:<14} sim={score:.2f} dur={len(audio) / 24000:.2f}s  heard={heard[:40]!r}")


if __name__ == "__main__":
    main()
