"""Проверка влияния алиасинга на оценку схожести голоса.

Сравнивает наивный ресемплинг (np.interp, без фильтра) и полифазный FIR
на одном и том же материале: как меняется ECAPA-эмбеддинг и тембр.

    python tools\\check_resample_quality.py
"""

from __future__ import annotations

import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)


def interp_resample(data: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    n_out = int(round(len(data) * sr_out / sr_in))
    x_old = np.linspace(0.0, 1.0, num=len(data), endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
    return np.interp(x_new, x_old, data).astype(np.float32)


def main() -> None:
    import soundfile as sf
    import voice_similarity as vs

    prof = vs.VoiceProfiler()
    src = os.path.join(ROOT, "out", "wav", "mx_01.wav")
    audio, sr = sf.read(src, dtype="float32")

    variants = {
        "без ресемплинга (44.1k -> 16k, np.interp)": interp_resample(audio, sr, 16000),
        "полифазный FIR (44.1k -> 16k)": vs.resample(audio, sr, 16000),
    }

    import tempfile
    tmp_dir = tempfile.mkdtemp(prefix="redz_rs_")

    paths = {}
    for name, data in variants.items():
        path = os.path.join(tmp_dir, "variant.wav")
        sf.write(path, data, 16000, subtype="PCM_16")
        paths[name] = path

    print("Сравнение тембра и схожести:\n")
    ref_emb = prof.embed(paths["полифазный FIR (44.1k -> 16k)"])
    for name, path in paths.items():
        emb = prof.embed(path)
        score = float(np.dot(ref_emb, emb))
        cent = vs.spectral_centroid(*sf.read(path, dtype="float32"))
        # сколько энергии утекло выше 8 кГц (признак алиасинга)
        spec = np.abs(np.fft.rfft(sf.read(path, dtype="float32")[0]))
        freqs = np.fft.rfftfreq(len(sf.read(path, dtype="float32")[0]), 1 / 16000)
        hot = spec[freqs > 8000].sum() / (spec.sum() + 1e-12)
        print(f"  {name:<44} ECAPA(к FIR)={score:+.3f}  центр={cent:6.0f}  энергия >8кГц={hot * 100:5.2f}%")


if __name__ == "__main__":
    main()
