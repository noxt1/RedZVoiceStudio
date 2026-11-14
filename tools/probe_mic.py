"""Проверка микрофона БЕЗ голоса: уровень сигнала и каналы.

Показывает, слышит ли устройство что-то (шум комнаты, дыхание) и какой
уровень. Если RMS заметно выше нуля — микрофон живой и запись будет
пригодна для распознавания.

Полный тест с распознаванием (нужен голос) — tools/test_mic.py.

    python tools\\probe_mic.py
"""

from __future__ import annotations

import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))


def main() -> None:
    import sounddevice as sd

    print("=== ВСЕ УСТРОЙСТВА ВВОДА ===")
    try:
        default_in = sd.default.device[0]
    except Exception:
        default_in = None
    inputs = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            mark = " (по умолчанию)" if i == default_in else ""
            print(f"  [{i:2d}] {d['name'][:52]:<52} ch={d['max_input_channels']} "
                  f"sr={int(d['default_samplerate'])}{mark}")
            inputs.append(i)
    print(f"  по умолчанию: {default_in}")

    # исключаем служебные (стерео микшер, обобщённые драйверы)
    real = []
    for i in inputs:
        try:
            name = sd.query_devices(i)["name"].lower()
        except Exception:
            continue
        if any(g in name for g in ("стерео микшер", "stereo mix", "первичный драйвер",
                                   "primary sound capture", "переназначение звуковых")):
            continue
        real.append(i)

    print(f"\n=== ПРОВЕРКА УРОВНЯ (по 2 с на устройство) ===")
    for idx in real[:4]:
        name = sd.query_devices(idx)["name"]
        try:
            sr = 44100
            rec = sd.rec(int(sr * 2), samplerate=sr, channels=1, dtype="float32",
                         device=idx)
            sd.wait()
            audio = np.asarray(rec, dtype="float32").squeeze()
        except Exception as exc:
            print(f"  [{idx}] {name[:44]:<44} ОШИБКА: {exc}")
            continue
        rms = float(np.sqrt((audio.astype(np.float64) ** 2).mean()))
        peak = float(np.abs(audio).max())
        verdict = ("живой" if rms > 0.004 else
                   "тихий, но не мёртв" if rms > 0.001 else "тишина")
        print(f"  [{idx}] {name[:44]:<44} RMS {rms:.5f} пик {peak:.3f} — {verdict}")

    print("\n=== ВЫВОД ===")
    print("Если RMS > 0.004 — микрофон слышит, запись пойдёт в распознавание.")
    print("Для полной проверки (с голосом) запусти research/test_mic.py")


if __name__ == "__main__":
    main()
