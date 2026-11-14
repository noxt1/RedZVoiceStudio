"""Тест движка живого перевода: запустить, загрузить, перевести аудио.

Проверяет протокол GUI <-> движок целиком, как это делает приложение.

Запуск:
    "<engine>\\Scripts\\python.exe" research\\test_live_engine.py
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import time

WS = os.path.join(os.environ.get("LOCALAPPDATA", ""), "RedZVoiceStudio", "workspace")
ENGINE = os.path.join(os.environ.get("LOCALAPPDATA", ""), "RedZVoiceStudio",
                      "engine", "Scripts", "python.exe")
SCRIPT = os.path.join(WS, "tools", "live_translate.py")
REF = os.path.join(WS, "reference.wav")
SAMPLES = os.path.join(WS, "voice_samples")


def main() -> None:
    import numpy as np
    import soundfile as sf

    if not os.path.exists(SCRIPT):
        sys.exit(f"нет движка: {SCRIPT}")

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["COQUI_TOS_AGREED"] = "1"
    env["PYTHONUNBUFFERED"] = "1"

    print("=== запуск движка ===")
    proc = subprocess.Popen([ENGINE, SCRIPT, f"--reference={REF}"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, encoding="utf-8",
                            errors="replace", bufsize=1, env=env,
                            cwd=os.path.dirname(SCRIPT))

    def send(msg: dict) -> None:
        proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
        proc.stdin.flush()

    def read_until(stop_events, timeout=180):
        out = []
        t0 = time.time()
        while time.time() - t0 < timeout:
            line = proc.stdout.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except Exception:
                print("  (не JSON):", line[:120])
                continue
            out.append(msg)
            if msg.get("event") in stop_events:
                return out
        return out

    print("  жду boot ...")
    read_until({"boot"}, timeout=60)

    print("=== загрузка моделей (15–30 с) ===")
    t0 = time.time()
    send({"cmd": "load"})
    msgs = read_until({"ready", "error"}, timeout=300)
    for m in msgs:
        if m.get("event") == "ready":
            print(f"  ГОТОВО за {time.time() - t0:.1f} с "
                  f"(load_ms={m.get('load_ms')}, asr_ms={m.get('asr_ms')})")
        elif m.get("event") == "error":
            print(f"  ОШИБКА: {m.get('message')}")
            print(m.get("traceback", "")[:1500])
            proc.kill()
            return

    # --- перевод реальной русской записи ---
    files = sorted(f for f in os.listdir(SAMPLES) if f.endswith(".wav"))[:3]
    for fname in files:
        path = os.path.join(SAMPLES, fname)
        audio, sr = sf.read(path, dtype="float32", always_2d=False)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        from math import gcd
        from scipy.signal import resample_poly
        g = gcd(int(sr), 16000)
        pcm16 = resample_poly(audio, 16000 // g, int(sr) // g).astype(np.float32)
        data = (np.clip(pcm16, -1, 1) * 32767).astype(np.int16)

        print(f"\n=== {fname} ({len(audio) / sr:.1f} с) ===")
        t0 = time.time()
        send({"cmd": "translate", "seq": 1,
              "pcm": base64.b64encode(data.tobytes()).decode("ascii")})
        chunks = 0
        first_chunk_ms = None
        text_msg = None
        done_ms = None
        t_first = None
        while True:
            line = proc.stdout.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except Exception:
                continue
            ev = msg.get("event")
            if ev == "text":
                text_msg = msg
                print(f"  RU: {msg.get('ru')}")
                print(f"  ES: {msg.get('es')}")
                print(f"  (распознавание {msg.get('asr_ms')} мс, "
                      f"перевод {msg.get('tr_ms')} мс)")
            elif ev == "chunk":
                chunks += 1
                if t_first is None:
                    t_first = time.time()
                    first_chunk_ms = int((t_first - t0) * 1000)
                    print(f"  >>> ПЕРВЫЙ ЗВУК через {first_chunk_ms} мс")
            elif ev == "done":
                done_ms = msg.get("ms")
                break
            elif ev == "error":
                print("  ОШИБКА:", msg.get("message"))
                print(msg.get("traceback", "")[:1200])
                break
        print(f"  чанков: {chunks} | до первого звука: {first_chunk_ms} мс | "
              f"синтез: {done_ms} мс")

    proc.stdin.write(json.dumps({"cmd": "quit"}) + "\n")
    proc.stdin.flush()
    time.sleep(1)
    proc.kill()
    print("\n=== тест завершён ===")


if __name__ == "__main__":
    main()
