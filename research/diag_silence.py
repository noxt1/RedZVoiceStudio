"""Диагностика: почему в тишине что-то озвучивается.

Снимает 6 секунд ТИШИНЫ с микрофона и прогоняет её через:
  1. VAD приложения (adaptive noise floor + порог);
  2. Whisper — что он «слышит» в тишине (галлюцинации);
  3. порог решения «есть ли речь».

Показывает, что нужно исправить.

    "<engine>\\Scripts\\python.exe" research\\diag_silence.py
"""

from __future__ import annotations

import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

import live_tab as lt  # noqa: E402


def pick_mic() -> int:
    import sounddevice as sd
    try:
        default_in = sd.default.device[0]
    except Exception:
        default_in = None
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            name = d["name"].lower()
            if any(g in name for g in ("стерео микшер", "stereo mix", "первичный драйвер",
                                       "primary sound capture", "переназначение звуковых")):
                continue
            if i == default_in:
                return i
    return 0


def main() -> None:
    import sounddevice as sd

    idx = pick_mic()
    print(f"микрофон: [{idx}] {sd.query_devices(idx)['name']}")
    print("записываю 6 секунд — ГОВОРИ НИЧЕГО (тишина)")

    sr = 44100
    rec = sd.rec(int(sr * 6), samplerate=sr, channels=1, dtype="float32", device=idx)
    sd.wait()
    audio = np.asarray(rec, dtype="float32").squeeze()
    rms = float(np.sqrt((audio.astype(np.float64) ** 2).mean()))
    peak = float(np.abs(audio).max())
    print(f"записано: RMS {rms:.5f}, пик {peak:.4f}")

    # --- 1. что делает VAD приложения ---
    print("\n=== 1. VAD приложения на этой тишине ===")
    obj = lt.LiveTab.__new__(lt.LiveTab)
    obj._cont_buf = []
    obj._cont_silence = 0.0
    obj._cont_has_speech = False
    obj._noise = 0.005
    obj._cont_on = True
    sent = []
    obj._queue_translate = lambda pcm, sr=44100: sent.append(pcm.copy())

    step = int(sr * lt.BLOCK_SEC)
    noise_trace = []
    for i in range(len(audio) // step):
        block = audio[i * step:(i + 1) * step]
        obj._cont_callback(block.reshape(-1, 1), 0, None, None)
        noise_trace.append(obj._noise)
    print(f"  фраз отправлено на перевод: {len(sent)}")
    print(f"  шумовой пол: начало {noise_trace[0]:.5f} -> конец {noise_trace[-1]:.5f}")
    thr_end = max(noise_trace[-1] * 3.0, 0.004)
    print(f"  порог в конце: {thr_end:.5f}  (уровень тишины {rms:.5f})")
    if sent:
        for i, p in enumerate(sent):
            print(f"  фраза [{i}]: {len(p) / sr:.2f} с, RMS "
                  f"{float(np.sqrt((p.astype(np.float64) ** 2).mean())):.5f}")

    # --- 2. что говорит Whisper на этой тишине ---
    print("\n=== 2. Whisper на записанной тишине ===")
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("mobiuslabsgmbh/faster-whisper-large-v3-turbo",
                             device="cuda", compute_type="float16")
        for label, x in (("как есть", audio),):
            t0 = time.time()
            segs, _ = model.transcribe(x, language="ru", beam_size=1,
                                       vad_filter=False,
                                       condition_on_previous_text=False,
                                       no_speech_threshold=0.8,
                                       log_prob_threshold=-2.0)
            txt = " ".join(s.text.strip() for s in segs)
            nsp = [getattr(s, "no_speech_prob", None) for s in segs]
            print(f"  [{label}] {time.time() - t0:.2f} с -> {txt!r}")
            print(f"    no_speech_prob: {nsp}")
            print(f"    пусто: {not txt.strip()}")
    except Exception as exc:
        print(f"  ошибка: {exc}")


if __name__ == "__main__":
    main()
