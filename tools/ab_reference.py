"""A/B-тест образца голоса: старый (длинный) против нового (чистый, 25 с).

Генерирует несколько фраз обоими образцами и сравнивает схожесть
с эталоном из сырых записей.

    python tools\\ab_reference.py
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

TEXTS = ["Que chido, guay!", "No se mueva!", "Auxilio!"]


def build_ground_truth() -> str:
    import soundfile as sf
    ws = sp.workspace()
    samples = sorted(glob.glob(os.path.join(ws, "voice_samples", "take_*.wav")))
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
    path = os.path.join(ws, "my_voice_ground_truth.wav")
    sf.write(path, ref, 44100, subtype="PCM_16")
    return path


def main() -> None:
    ws = sp.workspace()
    python = sp.engine_python()
    if not python:
        sys.exit("Нет движка")
    gt = build_ground_truth()

    candidates = {
        "старый (78 с, как было)": os.path.join(ws, "reference.wav"),
        "новый (25 с, по чистоте)": os.path.join(ws, "reference_new.wav"),
    }
    for name, path in candidates.items():
        if not os.path.exists(path):
            print(f"{name}: файла нет")
            continue
        import soundfile as sf
        dur = sf.info(path).duration
        out_dir = os.path.join(ws, f"ab_{abs(hash(name)) % 1000}")
        os.makedirs(out_dir, exist_ok=True)
        for i, text in enumerate(TEXTS):
            subprocess.run([python, os.path.join(ws, "tools", "xtts_clone.py"),
                            "--reference", path, "--text", text,
                            "--id", f"{i + 1:02d}", "--attempts", "2",
                            "--out", out_dir],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
        proc = subprocess.run(
            [python, os.path.join(ws, "tools", "voice_similarity.py"),
             "--reference", gt, "--wav-dir", os.path.join(out_dir, "wav")],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        summary = [l for l in proc.stdout.splitlines() if "Средняя схожесть" in l]
        print(f"{name} ({dur:.0f} с): {summary[0] if summary else 'нет данных'}")


if __name__ == "__main__":
    main()
