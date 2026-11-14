"""Диагностика: почему клон из некоторых референсов «не похож».

Сравнивает:
  * обычный вызов tts() с референсом
  * вызов с профилями сэмплирования из xtts_clone.py (в т.ч. split_sentences=False)

    python tools\\diagnose_clone_identity.py
"""

from __future__ import annotations

import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)
os.environ.setdefault("COQUI_TOS_AGREED", "1")

from xtts_clone import SAMPLING_PROFILES, patch_torchaudio  # noqa: E402

REFS = {
    "cand": r"C:\Users\cyril\AppData\Local\Temp\opencode\fleurs\ref_natural\cand.wav",
    "two0": r"C:\Users\cyril\AppData\Local\Temp\opencode\fleurs\two\10065021285799740602.wav",
}
TEXT = "Que chido, guay! Pinche cabron, no manches."


def main() -> None:
    import soundfile as sf
    import voice_similarity as vs
    from TTS.api import TTS

    patch_torchaudio()
    model = TTS(model_name="tts_models/multilingual/multi-dataset/xtts_v2",
                progress_bar=False).to("cuda")
    prof = vs.VoiceProfiler()

    for label, ref in REFS.items():
        if not os.path.exists(ref):
            print(f"{label}: референс отсутствует")
            continue
        ref_emb = prof.embed(ref)
        print(f"\n--- {label} ({os.path.basename(ref)})")
        for i, profile in enumerate(SAMPLING_PROFILES[:6]):
            kwargs = {"split_sentences": True}
            kwargs.update(profile)
            out = model.tts(text=TEXT, speaker_wav=ref, language="es", **kwargs)
            audio = np.asarray(out, dtype="float32")
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            path = os.path.join(os.path.dirname(ref), f"diag_{label}_{i}.wav")
            sf.write(path, audio, 24000, subtype="PCM_16")
            score = float(np.dot(ref_emb, prof.embed(path)))
            desc = ", ".join(f"{k}={v}" for k, v in profile.items()) or "base"
            print(f"  профиль {i} ECAPA={score:+.3f}  ({desc})")


if __name__ == "__main__":
    main()
