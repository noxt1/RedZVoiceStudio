"""Подбор темпа (length_scale) для каждой реплики.

Piper на быстром темпе (1.05) иногда «спотыкается» на коротких выкриках:
«Arriba!» звучит как «Adiós», «Abajo!» как «A ver». На 1.15-1.20 те же
фразы читаются верно.

Скрипт синтезирует каждую реплику на нескольких темпах, оценивает
разборчивость через Whisper и сохраняет лучший темп в tools/length_scales.json.
Дальше synthesize.py подхватывает эти значения.

    python tools\\optimize_tempo.py
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
SCALES = [1.05, 1.15, 1.25, 1.40]


def main() -> None:
    import soundfile as sf
    from faster_whisper import WhisperModel
    from piper import PiperVoice, SynthesisConfig

    import audio_post as ap

    with open(os.path.join(ROOT, "lines.json"), encoding="utf-8") as fh:
        lines = json.load(fh)["lines"]

    voice = PiperVoice.load(PIPER_M, config_path=PIPER_M_JSON)
    whisper = WhisperModel("medium", device="cpu", compute_type="int8")
    norm = lambda t: "".join(c for c in t.lower() if c.isalpha())

    def similarity(heard: str, expected: str) -> float:
        """0..1: насколько распознанное совпадает с ожидаемым."""
        h, e = norm(heard), norm(expected)
        if not e:
            return 1.0
        if h == e:
            return 1.0
        if not h:
            return 0.0
        pool = list(h)
        common = 0
        for ch in e:
            if ch in pool:
                pool.remove(ch)
                common += 1
        return common / len(e)

    best: dict[str, float] = {}
    report: list[str] = []

    for line in lines:
        lid, text = line["id"], line["es"]
        scored = []
        for ls in SCALES:
            sc = SynthesisConfig(length_scale=ls, noise_scale=0.55, noise_w_scale=0.8)
            raw = np.concatenate([c.audio_float_array for c in voice.synthesize(text, sc)]).astype("float32")
            processed = ap.process(raw, voice.config.sample_rate)
            audio16 = ap.to_16k(processed, ap.SR)
            # два прогона: с подсказкой (разборчивость) и без (естественность)
            segs, _ = whisper.transcribe(
                audio16, language="es", beam_size=5, vad_filter=False,
                condition_on_previous_text=False, initial_prompt=text,
            )
            biased = " ".join(s.text.strip() for s in segs).strip()
            segs2, _ = whisper.transcribe(
                audio16, language="es", beam_size=5, vad_filter=False,
                condition_on_previous_text=False,
            )
            free = " ".join(s.text.strip() for s in segs2).strip()
            s_biased = similarity(biased, text)
            s_free = similarity(free, text)
            # точное совпадение без подсказки — лучший признак «звучит как надо»
            score = s_free if s_free >= 0.999 else (s_biased * 0.9 + s_free * 0.1)
            scored.append((score, ls, free))
        scored.sort(key=lambda t: t[0], reverse=True)
        chosen = scored[0][1]
        best[lid] = chosen
        report.append(f"[{lid}] {text:<38} -> length_scale={chosen}  score={scored[0][0]:.2f}")
        print(report[-1], flush=True)

    out = os.path.join(ROOT, "tools", "length_scales.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(best, fh, ensure_ascii=False, indent=2)
    print(f"\nСохранено -> {out}")


if __name__ == "__main__":
    main()
