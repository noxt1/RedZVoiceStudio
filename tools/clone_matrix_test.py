"""Решающий тест клонирования: матрица схожести «референс x клон».

Берём два разных голоса, клонируем от каждого одну фразу и смотрим:
  * клон_A против референса_A (свой голос) — должно быть высоко
  * клон_A против референса_B (чужой голос) — должно быть низко

Если первое ≈ второе, клонирование не работает.

    python tools\\clone_matrix_test.py
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

REFS = [
    r"C:\Users\cyril\AppData\Local\Temp\opencode\fleurs\two\10065021285799740602.wav",
    r"C:\Users\cyril\AppData\Local\Temp\opencode\fleurs\two\10284528973491487253.wav",
]
TEXT = "Que chido, guay! Pinche cabron, no manches."


def main() -> None:
    import soundfile as sf
    import voice_similarity as vs
    from TTS.api import TTS

    patch_torchaudio()
    model = TTS(model_name="tts_models/multilingual/multi-dataset/xtts_v2",
                progress_bar=False).to("cuda")

    clones = []
    for i, ref in enumerate(REFS):
        out = model.tts(text=TEXT, speaker_wav=ref, language="es", split_sentences=True)
        audio = np.asarray(out, dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        path = os.path.join(os.path.dirname(REFS[0]), f"clone_{i}.wav")
        sf.write(path, audio, 24000, subtype="PCM_16")
        clones.append(path)

    prof = vs.VoiceProfiler()
    e = prof.embed

    print("\nECAPA: референс x клон\n")
    for i, ref in enumerate(REFS):
        print(f"  ref{i}: vs clone0={float(np.dot(e(ref), e(clones[0]))):+.3f} "
              f"vs clone1={float(np.dot(e(ref), e(clones[1]))):+.3f}  vs self=+1.000")
    for i, cl in enumerate(clones):
        print(f"  clone{i}: vs ref0={float(np.dot(e(cl), e(REFS[0]))):+.3f} "
              f"vs ref1={float(np.dot(e(cl), e(REFS[1]))):+.3f}")

    own = float(np.dot(e(clones[0]), e(REFS[0])))
    cross = float(np.dot(e(clones[0]), e(REFS[1])))
    print(f"\nСвой голос: {own:+.3f} | чужой голос: {cross:+.3f} | разница: {own - cross:+.3f}")
    if own - cross < 0.15:
        print("!! Клонирование НЕ сохраняет голос — клон звучит как попало.")
        raise SystemExit(1)
    print("Клонирование сохраняет голос.")


if __name__ == "__main__":
    main()
