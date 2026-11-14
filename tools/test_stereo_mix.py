"""Проверка: ловит ли «Стерео микшер» звук, идущий в наушники.

Играем тон в устройство вывода, которое захватывает Stereo Mix, и одновременно
пишем с самого Stereo Mix. Если тон виден — устройство рабочее.

    python tools\\test_stereo_mix.py
"""

from __future__ import annotations

import os
import sys
import threading
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

import hotkeys as hk  # noqa: E402

SR = 48000
TONE_HZ = 1000.0


def main() -> None:
    inputs, outputs = hk.list_devices()
    mix_i, mix_n = hk.find_stereo_mix(inputs)
    render_i, render_n = hk.find_render_for_capture(inputs, outputs)
    print(f"Stereo Mix: {mix_i} | {mix_n}")
    print(f"вывод     : {render_i} | {render_n}")

    if mix_i is None:
        sys.exit("Stereo Mix не найден")

    import sounddevice as sd

    # Пишем со Stereo Mix, параллельно играем тон в вывод
    chunks = []

    def record():
        try:
            with sd.InputStream(samplerate=SR, channels=1, dtype="float32",
                                device=mix_i) as st:
                for _ in range(int(SR * 4)):
                    data, _ = st.read(SR // 10)
                    chunks.append(data[:, 0].copy())
                    time.sleep(0.1)
        except Exception as exc:  # noqa: BLE001
            print("запись не удалась:", exc)

    t = threading.Thread(target=record, daemon=True)
    t.start()
    time.sleep(0.7)

    # Играем тон в вывод
    t0 = time.time()
    tone = (0.4 * np.sin(2 * np.pi * TONE_HZ * np.arange(SR * 3) / SR)).astype("float32")
    try:
        sd.play(tone, samplerate=SR, device=render_i)
    except Exception as exc:  # noqa: BLE001
        print("воспроизведение не удалось:", exc)
    while time.time() - t0 < 3.2:
        time.sleep(0.1)

    t.join(timeout=2)
    if not chunks:
        sys.exit("нет данных")

    audio = np.concatenate(chunks)
    spec = np.abs(np.fft.rfft(audio * np.hanning(len(audio))))
    freqs = np.fft.rfftfreq(len(audio), 1 / SR)
    peak_tone = float(spec[(freqs > TONE_HZ - 60) & (freqs < TONE_HZ + 60)].max())
    total = float(spec.sum()) + 1e-12
    print(f"\nзаписано {len(audio) / SR:.1f} c, пик {np.abs(audio).max():.4f}")
    print(f"энергия на {TONE_HZ} Гц: {peak_tone / total * 100:.3f}% всей энергии")
    if peak_tone / total > 0.005:
        print("ИТОГ: Stereo Mix ЗАХВАТЫВАЕТ звук — устройство рабочее.")
    else:
        print("ИТОГ: Stereo Mix не поймал тон — возможно, он не активен.")


if __name__ == "__main__":
    main()
