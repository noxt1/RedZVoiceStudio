"""Какое устройство записи слышит системный звук (нужно для перехвата).

Играем короткий звук в обычный выход и пробуем записать его разными
устройствами записи. Устройство с ненулевым пиком и годно для перехвата.

    python tools\\probe_capture.py
"""

from __future__ import annotations

import os
import sys
import threading
import time

import numpy as np

WS = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Auraloom", "workspace")
SR = 44100


def main() -> None:
    import sounddevice as sd
    import soundfile as sf

    clip = os.path.join(WS, "out", "mp3", "mx_01.mp3")
    data, sr = sf.read(clip, dtype="float32", always_2d=False)
    if data.ndim > 1:
        data = data.mean(axis=1)
    data = np.concatenate([data, np.zeros(int(sr * 0.6), dtype=np.float32)])

    print(f"вывод по умолчанию: {sd.default.device[1]} "
          f"{sd.query_devices()[sd.default.device[1]]['name']!r}")

    for idx in range(len(sd.query_devices())):
        d = sd.query_devices()[idx]
        if d["max_input_channels"] <= 0:
            continue
        blocks: list[np.ndarray] = []

        def cb(indata, frames, time_info, status, _b=blocks):  # noqa: ARG001
            try:
                _b.append(indata[:, 0].copy())
            except Exception:
                pass

        try:
            stream = sd.InputStream(device=idx, channels=1, samplerate=SR,
                                    dtype="float32", blocksize=1024, callback=cb)
            stream.start()
        except Exception as exc:  # noqa: BLE001
            print(f"  {idx:>3} {d['name']!r}: не открылся ({type(exc).__name__})")
            continue
        time.sleep(0.4)

        def play() -> None:
            try:
                sd.play(data, samplerate=sr)
                sd.wait()
            except Exception:
                pass

        threading.Thread(target=play, daemon=True).start()
        time.sleep(len(data) / sr + 0.5)
        try:
            stream.stop()
            stream.close()
        except Exception:
            pass
        if not blocks:
            print(f"  {idx:>3} {d['name']!r}: пусто")
            continue
        audio = np.concatenate(blocks)
        peak = float(np.abs(audio).max())
        rms = float(np.sqrt((audio.astype(np.float64) ** 2).mean()))
        mark = "  <-- СЛЫШИТ" if peak > 0.01 else ""
        print(f"  {idx:>3} {d['name']!r}: пик={peak:.3f} rms={rms:.4f}{mark}")


if __name__ == "__main__":
    main()
