"""Изоляция бага: как post-обработка меняет голос.

Сравнивает:
  * сырой выход XTTS (24 кГц)
  * process() с правильной входной частотой
  * process() с неправильной (как было в synthesize/xtts_clone)

    python tools\\diagnose_postprocess.py
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


def main() -> None:
    import soundfile as sf
    import voice_similarity as vs
    from TTS.api import TTS

    patch_torchaudio()
    model = TTS(model_name="tts_models/multilingual/multi-dataset/xtts_v2",
                progress_bar=False).to("cuda")
    out = model.tts(text="Que chido, guay! Pinche cabron, no manches.",
                    speaker_wav=REF, language="es", split_sentences=True)
    raw = np.asarray(out, dtype="float32")
    if raw.ndim > 1:
        raw = raw.mean(axis=1)
    raw_sr = 24000
    print(f"сырой XTTS: {len(raw) / raw_sr:.2f} c @ {raw_sr} Гц")

    prof = vs.VoiceProfiler()
    ref_emb = prof.embed(REF)

    def report(label: str, data: np.ndarray, sr_out: int) -> None:
        path = os.path.join(os.path.dirname(REF), "pp_tmp.wav")
        sf.write(path, data, sr_out, subtype="PCM_16")
        a, sr = sf.read(path, dtype="float32")
        f0 = vs.f0_median(vs.resample(a, sr, 16000), 16000)
        emb = prof.embed(path)
        print(f"  {label:<42} sr={sr:<6} F0={f0:6.1f} Гц  ECAPA={float(np.dot(ref_emb, emb)):+.3f}")

    import audio_post as ap
    report("сырой, записан как есть (24 кГц)", raw, raw_sr)
    report("process(raw, 24000) — входная частота верна", ap.process(raw, 24000), ap.SR)
    report("process(raw, 44100) — как было в коде", ap.process(raw, 44100), ap.SR)


if __name__ == "__main__":
    main()
