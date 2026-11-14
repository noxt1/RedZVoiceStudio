"""Диагностика: зависит ли ECAPA от длины клипа.

Короткие реплики (0.3-1.5 c) могут давать нестабильный эмбеддинг.
Проверяем: один и тот же референс, тексты разной длины.

    python tools\\diagnose_clip_duration.py
"""

from __future__ import annotations

import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)
os.environ.setdefault("COQUI_TOS_AGREED", "1")

from xtts_clone import patch_torchaudio  # noqa: E402

REF = r"C:\Users\cyril\AppData\Local\Temp\opencode\fleurs\ref_natural\cand.wav"
TEXTS = [
    "Que chido!",
    "Que chido, guay!",
    "Que chido, guay! Todo bien por aqui.",
    "No manches, carnal, vamos a trabajar hoy porque hace falta dinero.",
]


def main() -> None:
    import soundfile as sf
    import voice_similarity as vs
    from TTS.api import TTS

    patch_torchaudio()
    model = TTS(model_name="tts_models/multilingual/multi-dataset/xtts_v2",
                progress_bar=False).to("cuda")
    prof = vs.VoiceProfiler()
    ref_emb = prof.embed(REF)

    for i, text in enumerate(TEXTS):
        out = model.tts(text=text, speaker_wav=REF, language="es", split_sentences=True)
        audio = np.asarray(out, dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        path = os.path.join(os.path.dirname(REF), f"dur_{i}.wav")
        sf.write(path, audio, 24000, subtype="PCM_16")
        score = float(np.dot(ref_emb, prof.embed(path)))
        print(f"  {len(audio) / 24000:5.2f}s  ECAPA={score:+.3f}  {text[:44]}")


if __name__ == "__main__":
    main()
