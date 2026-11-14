"""Тест переключателя языка: русский -> испанский по нажатию.

Проверяет главное:
  1. при duck=True в кабель уходит ТОЛЬКО перевод (русский заглушен);
  2. после окончания перевода русский возвращается (duck=False).

Замер идёт через CABLE Output — как это услышит Discord.

    "<engine>\\Scripts\\python.exe" research\\test_lang_switch.py
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
    def __init__(self, device: int, sr: int):
        import sounddevice as sd
        self.blocks: list[np.ndarray] = []
        self._stream = sd.RawInputStream(device=device, channels=1, samplerate=sr,
                                        dtype="float32", blocksize=1024,
                                        callback=self._cb)
        self._stream.start()

    def _cb(self, indata, frames, time_info, status):  # noqa: ARG001
        self.blocks.append(np.asarray(indata, dtype=np.float32).copy())

    def stop(self) -> np.ndarray:
        try:
            self._stream.stop()
            self._stream.close()
        except Exception:
            pass
        if not self.blocks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(self.blocks)


def main() -> None:
    import sounddevice as sd

    devs = cable_mod.cable_devices()
    if not devs.get("output"):
        print("кабель не установлен")
        raise SystemExit(1)
    play_idx, play_name = devs["output"]
    rec_idx, rec_name = devs.get("input", (0, "CABLE Output"))
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

    # --- мост: микрофон + «перевод» ---
    bridge = mic_bridge.MicBridge(mic_device=mic_idx, render_device=play_idx,
                                  mic_gain=1.0, phrase_gain=1.0)
    bridge.start()
    time.sleep(0.6)

    # «микрофон» = громкий тон (имитация русской речи)
    t = np.arange(int(sr * 2.0)) / sr
    speech = (0.6 * np.sin(2 * np.pi * 300 * t)).astype(np.float32)
    es = (0.6 * np.sin(2 * np.pi * 700 * t)).astype(np.float32)

    print("\n=== 1. русский в кабеле (мост работает, заглушки нет) ===")
    cap = Capture(rec_idx, sr)
    time.sleep(0.3)
    bridge.push_pcm(speech, sr)          # имитация: микрофон говорит
    time.sleep(2.2)
    a1 = cap.stop()
    print(f"  пик {np.abs(a1).max():.1f} (есть сигнал: {np.abs(a1).max() > 1})")

    print("\n=== 2. нажали «язык»: русский заглушен, идёт перевод ===")
    bridge.set_duck(True)
    cap2 = Capture(rec_idx, sr)
    time.sleep(0.3)
    bridge.push_pcm(es, sr)
    time.sleep(2.2)
    a2 = cap2.stop()
    peak2 = float(np.abs(a2).max())
    print(f"  пик {peak2:.1f} (перевод идёт: {peak2 > 1})")

    print("\n=== 3. перевод дозвучал, русский вернулся ===")
    bridge.set_duck(False)
    cap3 = Capture(rec_idx, sr)
    time.sleep(0.3)
    bridge.push_pcm(speech, sr)
    time.sleep(2.2)
    a3 = cap3.stop()
    peak3 = float(np.abs(a3).max())
    print(f"  пик {peak3:.1f} (русский вернулся: {peak3 > 1})")
    bridge.stop()

    ok = peak2 > 1 and peak3 > 1

    # --- 4. ЧИСЛЕННО: при заглушке русский действительно исчезает ---
    print("\n=== 4. точно: в заглушке микрофона нет ===")
    frames = 1024
    # подкладываем «микрофон» = 0.9 и «перевод» = 0.1
    bridge._mic_blocks.clear()
    bridge._mic_blocks.append(np.full(frames, 0.9, dtype=np.float32))
    bridge._stream_q.clear()
    bridge._stream_q.append(np.full(frames, 0.1, dtype=np.float32))

    def mix_with(ducked: bool) -> float:
        bridge._mic_blocks.clear()
        bridge._mic_blocks.append(np.full(frames, 0.9, dtype=np.float32))
        bridge._stream_q.clear()
        bridge._stream_q.append(np.full(frames, 0.1, dtype=np.float32))
        bridge.set_duck(ducked)
        out = np.zeros((frames, 1), dtype=np.float32)
        bridge._out_callback(out, frames, None, None)
        return float(out[:, 0].mean())

    m_open = mix_with(False)
    m_duck = mix_with(True)
    print(f"  без заглушки: среднее {m_open:.3f} (микрофон слышен)")
    print(f"  с заглушкой:  среднее {m_duck:.3f} (только перевод)")
    mic_gone = m_duck < 0.15 and m_open > 0.5
    print(f"  русский исчезает, остаётся только перевод: {'ок' if mic_gone else 'ошибка'}")
    bridge.set_duck(False)

    print("\n=== ИТОГ ===")
    print(f"  переключение языка работает: {'ок' if ok and mic_gone else 'ошибка'}")
    if not (ok and mic_gone):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
