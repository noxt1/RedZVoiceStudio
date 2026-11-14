"""Подбор параметров Piper для плохо распознаваемых реплик.

Короткие выкрики («A huevo!», «Arriba!») при length_scale ~1.05 звучат
скомканно — ASR их путает. Проверяем, какой length_scale (темп) даёт
лучшую разборчивость, и пересобираем проблемные реплики.

    python tools\\fix_shorts.py
"""

from __future__ import annotations

import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)

PIPER_M = r"C:\Users\cyril\AppData\Local\Temp\opencode\es_MX-ald-medium.onnx"
PIPER_M_JSON = r"C:\Users\cyril\AppData\Local\Temp\opencode\es_MX-ald-medium.onnx.json"

# Реплики, которые ASR путает
PROBLEM_IDS = ["04", "08", "11", "13", "17", "28", "30"]
LENGTH_SCALES = [1.05, 1.20, 1.35, 1.50]


def main() -> None:
    import json
    import soundfile as sf
    from faster_whisper import WhisperModel
    from piper import PiperVoice, SynthesisConfig

    import audio_post as ap

    with open(os.path.join(ROOT, "lines.json"), encoding="utf-8") as fh:
        lines = {l["id"]: l for l in json.load(fh)["lines"]}

    voice = PiperVoice.load(PIPER_M, config_path=PIPER_M_JSON)
    whisper = WhisperModel("medium", device="cpu", compute_type="int8")

    def heard(audio: np.ndarray) -> str:
        segs, _ = whisper.transcribe(
            ap.to_16k(audio, ap.SR), language="es", beam_size=5, vad_filter=False,
            condition_on_previous_text=False,
        )
        return " ".join(s.text.strip() for s in segs).strip()

    norm = lambda t: "".join(c for c in t.lower() if c.isalpha())

    best_by_id = {}
    for lid in PROBLEM_IDS:
        text = lines[lid]["es"]
        print(f"\n[{lid}] {text}")
        for ls in LENGTH_SCALES:
            sc = SynthesisConfig(length_scale=ls, noise_scale=0.55, noise_w_scale=0.8)
            raw = np.concatenate([c.audio_float_array for c in voice.synthesize(text, sc)]).astype("float32")
            processed = ap.process(raw, voice.config.sample_rate)
            h = heard(processed)
            ok = norm(h) == norm(text)
            print(f"   length_scale={ls:<5} {'OK ' if ok else '!! '} {h[:40]!r} ({len(processed) / ap.SR:.2f}s)")
            if ok and lid not in best_by_id:
                best_by_id[lid] = ls

    print("\nЛучшие length_scale:", best_by_id)
    out = os.path.join(ROOT, "tools", "length_scales.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(best_by_id, fh, ensure_ascii=False, indent=2)
    print(f"Сохранено -> {out}")


if __name__ == "__main__":
    main()
