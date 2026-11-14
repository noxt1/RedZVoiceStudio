"""Проверка микрофона: запись -> распознавание -> перевод.

Проверяет весь путь с реального микрофона:
  1. микрофон вообще слышит (уровень сигнала);
  2. запись читается моделью (Whisper даёт осмысленный текст);
  3. перевод на испанский работает.

Просит наговорить фразу; ждёт тишины и сам заканчивает запись.

    "<engine>\\Scripts\\python.exe" research\\test_mic.py
"""

from __future__ import annotations

import os
import sys
import time

import numpy as np

WS = os.path.join(os.environ.get("LOCALAPPDATA", ""), "RedZVoiceStudio", "workspace")
ENGINE = os.path.join(os.environ.get("LOCALAPPDATA", ""), "RedZVoiceStudio",
                      "engine", "Scripts", "python.exe")
SCRIPT = os.path.join(WS, "tools", "live_translate.py")
REF = os.path.join(WS, "reference.wav")
OUT = os.path.join(WS, "logs", "mic_test.wav")

PHRASE = "Нет, брат, ты чего тут делаешь? Опять пьяный?"


def pick_mic() -> tuple[int, str]:
    """Выбрать микрофон по умолчанию (или первый реальный)."""
    import sounddevice as sd
    try:
        default_in = sd.default.device[0]
    except Exception:
        default_in = None
    best = None
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] <= 0:
            continue
        name = d["name"].lower()
        if any(g in name for g in ("стерео микшер", "stereo mix", "первичный драйвер",
                                   "primary sound capture", "переназначение звуковых")):
            continue
        if i == default_in:
            best = (i, d["name"])
            break
        if best is None:
            best = (i, d["name"])
    return best if best else (0, "?")


def record_until_silence(device: int, max_sec: float = 12.0,
                         silence_sec: float = 1.2) -> np.ndarray:
    """Записывать, пока есть речь; закончить после паузы тишины."""
    import sounddevice as sd
    sr = 44100
    blocks = []
    quiet = 0.0
    block_sec = 0.05
    started = False
    t0 = time.time()
    with sd.InputStream(device=device, channels=1, samplerate=sr, dtype="float32",
                        blocksize=int(sr * block_sec)) as stream:
        while time.time() - t0 < max_sec:
            data, _ = stream.read(int(sr * block_sec))
            mono = data[:, 0].copy()
            rms = float(np.sqrt((mono.astype(np.float64) ** 2).mean()))
            if rms > 0.006:
                started = True
                quiet = 0.0
            elif started:
                quiet += block_sec
            blocks.append(mono)
            if started and quiet >= silence_sec:
                break
    audio = np.concatenate(blocks) if blocks else np.zeros(0, dtype=np.float32)
    return audio if started else audio


def main() -> None:
    import soundfile as sf

    idx, name = pick_mic()
    print(f"микрофон: [{idx}] {name}")
    print(f"наговори: «{PHRASE}» (запись остановится после паузы)")
    time.sleep(1.5)

    audio = record_until_silence(idx)
    if audio.size == 0:
        print("НЕ ЗАПИСАНО: микрофон молчит")
        raise SystemExit(1)

    rms = float(np.sqrt((audio.astype(np.float64) ** 2).mean()))
    peak = float(np.abs(audio).max())
    dur = len(audio) / 44100
    print(f"записано {dur:.1f} с, RMS {rms:.4f}, пик {peak:.3f}")
    if rms < 0.004:
        print("ПРЕДУПРЕЖДЕНИЕ: сигнал очень тихий")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    sf.write(OUT, audio, 44100)
    print(f"сохранено: {OUT}")

    # --- проверяем распознавание и перевод ---
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["COQUI_TOS_AGREED"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    import base64
    import json
    import subprocess

    proc = subprocess.Popen([ENGINE, SCRIPT, f"--reference={REF}"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                            errors="replace", bufsize=1, env=env,
                            cwd=os.path.dirname(SCRIPT))

    def send(msg: dict) -> None:
        proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
        proc.stdin.flush()

    send({"cmd": "load"})
    while True:
        line = proc.stdout.readline()
        if not line:
            print("движок упал")
            raise SystemExit(1)
        try:
            msg = json.loads(line)
        except Exception:
            continue
        if msg.get("event") == "ready":
            print("движок готов")
            break
        if msg.get("event") == "error":
            print(f"ошибка: {msg.get('message')}")
            raise SystemExit(1)

    data = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    send({"cmd": "translate", "seq": 1, "sr": 44100,
          "pcm": base64.b64encode(data.tobytes()).decode("ascii")})

    ru = es = ""
    while True:
        line = proc.stdout.readline()
        if not line:
            break
        try:
            msg = json.loads(line)
        except Exception:
            continue
        if msg.get("event") == "text":
            ru = msg.get("ru", "")
            es = msg.get("es", "")
            print(f"\nРАСПОЗНАНО (RU): {ru}")
            print(f"ПЕРЕВОД   (ES): {es}")
        elif msg.get("event") in ("done", "error"):
            break

    proc.stdin.write(json.dumps({"cmd": "quit"}) + "\n")
    proc.stdin.flush()
    time.sleep(0.5)
    proc.kill()

    print("\n=== ИТОГ ===")
    print(f"микрофон слышит: {'да' if rms > 0.004 else 'НЕТ (тишина)'}")
    print(f"речь распознана: {'да' if ru else 'НЕТ'}")
    print(f"перевод получен: {'да' if es else 'НЕТ'}")


if __name__ == "__main__":
    main()
