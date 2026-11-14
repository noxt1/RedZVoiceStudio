"""Собрать эталон «твой настоящий голос» из сырых записей и измерить схожесть клона.

    python tools\\measure_own_voice.py

Эталон строится из самих записей подсказок (без пересборки), поэтому это
независимая мера: насколько клон похож на исходный голос.
"""

from __future__ import annotations

import glob
import os
import subprocess
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

import studio_paths as sp  # noqa: E402


def main() -> None:
    import soundfile as sf

    ws = sp.workspace()
    samples = sorted(glob.glob(os.path.join(ws, "voice_samples", "take_*.wav")))
    if not samples:
        sys.exit("Нет записей подсказок — сначала запиши их на вкладке «Голос».")

    parts = []
    for f in samples[:6]:
        audio, sr = sf.read(f, dtype="float32", always_2d=False)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        parts.append(audio)
        parts.append(np.zeros(int(sr * 0.35), dtype="float32"))
    ref = np.concatenate(parts)
    peak = float(np.abs(ref).max())
    if peak > 0:
        ref = ref / peak * 0.95
    ref_path = os.path.join(ws, "my_voice_ground_truth.wav")
    sf.write(ref_path, ref, 44100, subtype="PCM_16")
    print(f"Эталон из {min(6, len(samples))} записей: {len(ref) / 44100:.1f} с -> {ref_path}\n")

    python = sp.engine_python()
    if not python:
        sys.exit("Нет движка — см. tools\\setup_env.ps1")
    script = os.path.join(ws, "tools", "voice_similarity.py")
    if not os.path.exists(script):
        sys.exit("Нет voice_similarity.py в рабочей папке")

    proc = subprocess.run([python, script, "--reference", ref_path,
                           "--wav-dir", os.path.join(ws, "out", "wav")],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(proc.stdout[-2500:])
    if proc.stderr.strip():
        print(proc.stderr[-800:], file=sys.stderr)


if __name__ == "__main__":
    main()
