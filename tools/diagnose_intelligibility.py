"""Диагностика разборчивости: сырой синтез vs постобработка.

Если реплику не распознаёт ASR только после нормализации — виновата
обработка (trim/нормализация/фейды), а не голос.

    python tools\\diagnose_intelligibility.py
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)

PIPER_M = r"C:\Users\cyril\AppData\Local\Temp\opencode\es_MX-ald-medium.onnx"
PIPER_M_JSON = r"C:\Users\cyril\AppData\Local\Temp\opencode\es_MX-ald-medium.onnx.json"
IDS = ["04", "11", "13", "17", "30"]


def main() -> None:
    import soundfile as sf
    from faster_whisper import WhisperModel
    from piper import PiperVoice, SynthesisConfig

    import audio_post as ap

    with open(os.path.join(ROOT, "lines.json"), encoding="utf-8") as fh:
        lines = {l["id"]: l for l in json.load(fh)["lines"]}

    voice = PiperVoice.load(PIPER_M, config_path=PIPER_M_JSON)
    whisper = WhisperModel("medium", device="cpu", compute_type="int8")

    def heard(audio: np.ndarray, sr: int) -> str:
        segs, _ = whisper.transcribe(
            ap.to_16k(audio, sr), language="es", beam_size=5, vad_filter=False,
            condition_on_previous_text=False,
        )
        return " ".join(s.text.strip() for s in segs).strip()

    norm = lambda t: "".join(c for c in t.lower() if c.isalpha())

    for lid in IDS:
        text = lines[lid]["es"]
        sc = SynthesisConfig(length_scale=1.05, noise_scale=0.55, noise_w_scale=0.8)
        raw = np.concatenate([c.audio_float_array for c in voice.synthesize(text, sc)]).astype("float32")
        sr = voice.config.sample_rate

        variants = {
            "сырой синтез": raw,
            "только ресемплинг": ap.resample(raw, sr, ap.SR),
            "trim": ap.trim_silence(ap.resample(raw, sr, ap.SR), ap.SR),
            "trim+нормализация": ap.normalize(ap.trim_silence(ap.resample(raw, sr, ap.SR), ap.SR)),
            "полный process()": ap.process(raw, sr),
        }
        print(f"\n[{lid}] {text}")
        for label, audio in variants.items():
            h = heard(audio, ap.SR)
            ok = norm(h) == norm(text)
            print(f"   {'OK ' if ok else '!! '} {label:<22} {h[:38]!r}")


if __name__ == "__main__":
    main()
