"""Сквозной тест маршрута через виртуальный кабель (надёжный захват).

Проверяет ВСЮ цепочку, как её увидит Discord:
    микрофон (Fifine) + «реплика» -> мост -> CABLE Input
        -> CABLE Output (пишем его) -> проверяем, что звук есть

Захват идёт через callback (sd.rec отдаёт буфер с неинициализированной
памятью — из-за него мерялся «мусор»).

    "<engine>\\Scripts\\python.exe" research\\test_cable_route.py
"""

from __future__ import annotations

import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

import cable as cable_mod  # noqa: E402
import mic_bridge  # noqa: E402


class Capture:
    """Запись устройства через callback — только реальные samples."""

    def __init__(self, device: int, sr: int):
        import sounddevice as sd
        self.blocks: list[np.ndarray] = []
        self.sr = sr
        self._stream = sd.RawInputStream(device=device, channels=1, samplerate=sr,
                                        dtype="float32", blocksize=1024,
                                        callback=self._cb)
        self._stream.start()

    def _cb(self, indata, frames, time_info, status):  # noqa: ARG001
        self.blocks.append(np.asarray(indata, dtype=np.float32).copy())

    def stop(self) -> np.ndarray:
        import sounddevice as sd
        try:
            self._stream.stop()
            self._stream.close()
        except Exception:
            pass
        if not self.blocks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(self.blocks)


def level(a: np.ndarray) -> tuple[float, float]:
    if a.size == 0:
        return 0.0, 0.0
    return (float(np.sqrt((a.astype(np.float64) ** 2).mean())),
            float(np.abs(a).max()))


def main() -> None:
    import sounddevice as sd

    devs = cable_mod.cable_devices()
    print("=== устройства кабеля ===")
    print(" ", devs)
    if not devs.get("output"):
        print("кабель не установлен")
        raise SystemExit(1)
    play_idx, play_name = devs["output"]
    rec_idx, rec_name = devs.get("input", (0, "CABLE Output"))

    # пары устройств идут на разных частотах (44.1 и 48 кГц) — берём
    # те, что совпадают по частоте
    sr = int(sd.query_devices(play_idx)["default_samplerate"])
    if int(sd.query_devices(rec_idx)["default_samplerate"]) != sr:
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] > 0 and "cable" in d["name"].lower() \
                    and int(d["default_samplerate"]) == sr:
                rec_idx, rec_name = i, d["name"]
                break
    print(f"  играем в:  [{play_idx}] {play_name} ({sr} Гц)")
    print(f"  читаем из: [{rec_idx}] {rec_name}")

    mic_idx = None
    try:
        default_in = sd.default.device[0]
    except Exception:
        default_in = None
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] <= 0:
            continue
        low = d["name"].lower()
        if any(g in low for g in ("стерео микшер", "stereo mix", "первичный драйвер",
                                  "cable", "vb-audio", "переназначение звуковых")):
            continue
        if i == default_in:
            mic_idx = i
            break
        if mic_idx is None:
            mic_idx = i
    print(f"  микрофон:  [{mic_idx}] {sd.query_devices(mic_idx)['name']}")

    # --- 1. кабель сам по себе ---
    print("\n=== 1. CABLE Input -> CABLE Output ===")
    cap = Capture(rec_idx, sr)
    time.sleep(0.4)
    t = np.arange(int(sr * 1.5)) / sr
    tone = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    sd.play(tone, samplerate=sr, device=play_idx)
    time.sleep(2.2)
    sd.wait()
    time.sleep(0.3)
    audio = cap.stop()
    rms, peak = level(audio)
    print(f"  в CABLE Output: RMS {rms:.5f}, пик {peak:.4f} ({len(audio) / sr:.1f} с)")
    ok_cable = rms > 0.005
    print(f"  кабель работает: {'ок' if ok_cable else 'ТИШИНА'}")

    # --- 2. мост: микрофон + «реплика» -> кабель ---
    print("\n=== 2. мост (микрофон + фраза) -> CABLE Output ===")
    cap2 = Capture(rec_idx, sr)
    bridge = mic_bridge.MicBridge(mic_device=mic_idx, render_device=play_idx,
                                  mic_gain=1.0, phrase_gain=1.0)
    bridge.start()
    time.sleep(0.6)
    bridge.push_pcm(tone, sr)
    time.sleep(2.5)
    audio2 = cap2.stop()
    bridge.stop()
    rms2, peak2 = level(audio2)
    print(f"  через мост: RMS {rms2:.5f}, пик {peak2:.4f}")
    ok_bridge = peak2 > 0.05
    print(f"  мост доставляет звук: {'ок' if ok_bridge else 'ТИШИНА'}")

    print("\n=== ИТОГ ===")
    print(f"  кабель (CABLE Input -> CABLE Output): {'ок' if ok_cable else 'ошибка'}")
    print(f"  мост микрофон+фраза -> кабель:     {'ок' if ok_bridge else 'ошибка'}")
    if ok_cable and ok_bridge:
        print("\n  В Discord/игре микрофоном выбирай «CABLE Output».")


if __name__ == "__main__":
    main()
