"""Честная проверка аудиоустройств: какие реально открываются.

Важно: проверять нужно именно через InputStream/OutputStream с чтением из
потока. Раньше использовался sd.rec(), который открывает СВОЙ поток на
устройстве по умолчанию и тем самым проверял не то устройство.

    python tools\\probe_devices.py
"""

from __future__ import annotations

import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

RATES = (48000, 44100, 32000, 16000)


def probe_input(idx: int) -> list[int]:
    """Частоты, на которых вход реально открывается и отдаёт данные."""
    import sounddevice as sd
    ok = []
    for rate in RATES:
        try:
            with sd.InputStream(samplerate=rate, channels=1, dtype="float32",
                                device=idx, blocksize=1024) as st:
                data, _ = st.read(int(rate * 0.15))
            if len(data):
                ok.append(rate)
        except Exception:
            continue
    return ok


def probe_output(idx: int) -> list[int]:
    """Частоты, на которых выход реально открывается."""
    import sounddevice as sd
    ok = []
    for rate in RATES:
        try:
            with sd.OutputStream(samplerate=rate, channels=1, dtype="float32",
                                 device=idx, blocksize=1024) as st:
                st.write(np.zeros(int(rate * 0.1), dtype="float32"))
        except Exception:
            continue
        ok.append(rate)
    return ok


def main() -> None:
    import sounddevice as sd
    devices = sd.query_devices()
    inputs = [(i, d["name"]) for i, d in enumerate(devices) if d["max_input_channels"] > 0]
    outputs = [(i, d["name"]) for i, d in enumerate(devices) if d["max_output_channels"] > 0]

    print("=== ВХОДЫ ===")
    good_in = []
    for idx, name in inputs:
        rates = probe_input(idx)
        if rates:
            good_in.append((idx, name, rates))
            print(f"{idx:>4}  {name[:44]:<46} {rates}")
        else:
            print(f"{idx:>4}  {name[:44]:<46} — не открывается")

    print("\n=== ВЫХОДЫ ===")
    good_out = []
    for idx, name in outputs:
        rates = probe_output(idx)
        if rates:
            good_out.append((idx, name, rates))
            print(f"{idx:>4}  {name[:44]:<46} {rates}")
        else:
            print(f"{idx:>4}  {name[:44]:<46} — не открывается")

    print("\n=== ИТОГ ===")
    print("Рабочие микрофоны:")
    for idx, name, _ in good_in:
        print(f"   {idx:>4}  {name}")
    print("Рабочие выходы:")
    for idx, name, _ in good_out:
        print(f"   {idx:>4}  {name}")

    loop = [(i, n) for i, n, _ in good_in
            if any(k in n.lower() for k in ("стерео микшер", "stereo mix", "loopback"))]
    print("\nРабочий loopback:", loop or "нет (в игре его тоже не будет)")


if __name__ == "__main__":
    main()
