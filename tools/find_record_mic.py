"""Найти тот индекс микрофона, которым реально записывались подсказки.

Fifine-микрофон виден в системе несколько раз (разные API/частоты).
Сравниваем «шумовую подпись» (уровень шума и спектр тишины) записи с тишиной
каждого кандидата — совпадение укажет нужный.

    python tools\\find_record_mic.py
"""

from __future__ import annotations

import glob
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

import sounddevice as sd  # noqa: E402
import soundfile as sf  # noqa: E402
import studio_paths as sp  # noqa: E402

SR = 44100


def signature(audio: np.ndarray, sr: int = SR) -> tuple[float, float]:
    """(уровень шума, центроид спектра тишины) — «подпись» устройства."""
    win = max(1, int(sr * 0.02))
    n = len(audio) // win
    if n < 4:
        return 0.0, 0.0
    frames = audio[: n * win].reshape(n, win)
    rms = np.sqrt((frames.astype(np.float64) ** 2).mean(axis=1))
    floor = float(np.percentile(rms, 20))
    spec = np.abs(np.fft.rfft(audio[: min(len(audio), sr * 3)]))
    freqs = np.fft.rfftfreq(min(len(audio), sr * 3), 1 / sr)
    centroid = float(np.sum(spec * freqs) / (np.sum(spec) + 1e-12))
    return floor, centroid


def main() -> None:
    ws = sp.workspace()
    takes = sorted(glob.glob(os.path.join(ws, "voice_samples", "take_*.wav")))
    if not takes:
        sys.exit("Нет записей подсказок")

    floors, cents = [], []
    for f in takes[:6]:
        a, sr = sf.read(f, dtype="float32")
        if a.ndim > 1:
            a = a.mean(axis=1)
        fl, ct = signature(a, sr)
        floors.append(fl)
        cents.append(ct)
    ref_floor = float(np.mean(floors))
    ref_cent = float(np.mean(cents))
    print(f"Эталон (твои записи): шум {ref_floor:.6f}, центроид {ref_cent:.0f} Гц\n")

    devices = sd.query_devices()
    cands = [(i, d["name"]) for i, d in enumerate(devices)
              if d["max_input_channels"] > 0 and "fifine" in d["name"].lower()]
    if not cands:
        cands = [(i, d["name"]) for i, d in enumerate(devices)
                  if d["max_input_channels"] > 0]

    print(f"{'idx':>4}  {'устройство':<40} {'шум':>10} {'центроид':>9}  совпадение")
    best = None
    for idx, name in cands:
        try:
            rec = sd.rec(int(2 * SR), samplerate=SR, channels=1, dtype="float32",
                         device=idx)
            sd.wait()
            audio = np.asarray(rec, dtype="float32").squeeze()
            fl, ct = signature(audio)
        except Exception as exc:  # noqa: BLE001
            print(f"{idx:>4}  {name[:40]:<40}  ошибка: {exc}")
            continue
        # чем ближе шум и центроид к эталону, тем вероятнее это тот же микрофон
        d_noise = abs(fl - ref_floor) / (ref_floor + 1e-9)
        d_cent = abs(ct - ref_cent) / (ref_cent + 1e-9)
        score = d_noise + d_cent
        print(f"{idx:>4}  {name[:40]:<40} {fl:10.6f} {ct:9.0f}  {score:8.3f}")
        if best is None or score < best[0]:
            best = (score, idx, name)

    if best:
        score, idx, name = best
        print(f"\nЛучший кандидат: #{idx} «{name}» (расхождение {score:.3f})")
        import json
        with open(os.path.join(ws, "last_mic.json"), "w", encoding="utf-8") as fh:
            json.dump({"index": int(idx), "name": name}, fh, ensure_ascii=False)
        print("Запомнен в last_mic.json — мост и запись будут использовать его.")


if __name__ == "__main__":
    main()
