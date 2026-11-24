"""Проверка качества: turbo float16 против turbo int8_float16.

int8_float16 экономит ~1.2 ГБ VRAM и ускоряет распознавание в ~2.4 раза.
Но квантование может портить текст — надо сравнить на ВСЕХ записях
пользователя, а не на одной.

Эталоном считаем float16 (текущий вариант): сравниваем, какие слова
разъезжаются.

    "<engine>\\Scripts\\python.exe" research\\bench_int8_quality.py
"""

from __future__ import annotations

import glob
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WS = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Auraloom", "workspace")


def main() -> None:
    import soundfile as sf
    from faster_whisper import WhisperModel

    clips = []
    for path in sorted(glob.glob(os.path.join(WS, "voice_samples", "*.wav"))):
        a, sr = sf.read(path, dtype="float32", always_2d=False)
        if a.ndim > 1:
            a = a.mean(axis=1)
        from math import gcd

        from scipy.signal import resample_poly
        if sr != 16000:
            g = gcd(int(sr), 16000)
            a = resample_poly(a, 16000 // g, int(sr) // g).astype(np.float32)
        clips.append((os.path.basename(path), a))

    results = {}
    times = {}
    for label, compute in (("float16", "float16"), ("int8_float16", "int8_float16")):
        model = WhisperModel("mobiuslabsgmbh/faster-whisper-large-v3-turbo",
                             device="cuda", compute_type=compute)
        texts, ts = [], []
        for _name, audio in clips:
            t0 = time.time()
            segs, _ = model.transcribe(audio, language="ru", beam_size=1,
                                       vad_filter=False,
                                       condition_on_previous_text=False)
            texts.append(" ".join(s.text.strip() for s in segs).strip())
            ts.append((time.time() - t0) * 1000)
        results[label] = texts
        times[label] = float(np.mean(ts))
        del model
        import torch
        torch.cuda.empty_cache()
        time.sleep(1)

    print(f"\n  среднее время распознавания: float16 {times['float16']:.0f} мс, "
          f"int8 {times['int8_float16']:.0f} мс")
    print(f"\n  {'файл':<16}{'совпало':>9}  различие")
    same_words = total_words = 0
    for (name, _a), f16, i8 in zip(clips, results["float16"],
                                   results["int8_float16"]):
        w16 = f16.lower().replace(",", "").split()
        w8 = i8.lower().replace(",", "").split()
        common = sum(1 for w in w16 if w in w8)
        same_words += common
        total_words += max(len(w16), len(w8))
        mark = "да" if f16 == i8 else "нет"
        diff = "" if f16 == i8 else f"\n      float16: {f16}\n      int8   : {i8}"
        print(f"  {name:<16}{mark:>9}{diff}")
    print(f"\n  совпало слов: {same_words} из {total_words} "
          f"({same_words / max(1, total_words):.0%})")


if __name__ == "__main__":
    main()
