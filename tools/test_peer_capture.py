"""Сквозной тест перехвата речи игроков.

Идея: играем испанскую реплику (озвучка mx_01.mp3) в обычный выход
(наушники), одновременно пишем «Стерео микшер» (он слышит всё, что
играет в системе) и отдаём запись движку в режим перехвата. Должны
получить испанский текст и его перевод на русский.

    python tools\\test_peer_capture.py
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import threading
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WS = os.path.join(os.environ.get("LOCALAPPDATA", ""), "RedZVoiceStudio", "workspace")
ENG = os.path.join(os.environ.get("LOCALAPPDATA", ""), "RedZVoiceStudio",
                   "engine", "Scripts", "python.exe")
SCRIPT = os.path.join(WS, "tools", "live_translate.py")
REF = os.path.join(WS, "reference.wav")
SR = 44100


def find_stereo_mix() -> int | None:
    """Номер устройства «Стерео микшер» / Stereo Mix."""
    try:
        import sounddevice as sd
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] <= 0:
                continue
            low = str(d["name"]).lower()
            if "стерео микшер" in low or "stereo mix" in low:
                return i
    except Exception:
        pass
    return None


def main() -> int:
    dev = find_stereo_mix()
    if dev is None:
        print("нет «Стерео микшера» — перехват проверить нечем")
        return 1
    print(f"устройство записи: {dev}")

    import sounddevice as sd
    import soundfile as sf

    clip = os.path.join(WS, "out", "mp3", "mx_01.mp3")
    if not os.path.exists(clip):
        print("нет озвучки mx_01.mp3")
        return 1
    data, sr = sf.read(clip, dtype="float32", always_2d=False)
    if data.ndim > 1:
        data = data.mean(axis=1)

    # --- запись ---
    blocks: list[np.ndarray] = []

    def cb(indata, frames, time_info, status):  # noqa: ARG001
        blocks.append(indata[:, 0].copy())

    stream = sd.InputStream(device=dev, channels=1, samplerate=SR,
                            dtype="float32", blocksize=1024, callback=cb)
    stream.start()
    time.sleep(0.7)

    # --- проигрываем реплику в обычный выход (как это делает игра) ---
    def play() -> None:
        try:
            sd.play(data, samplerate=sr)
            sd.wait()
        except Exception as exc:  # noqa: BLE001
            print("не удалось проиграть:", exc)

    threading.Thread(target=play, daemon=True).start()
    time.sleep(len(data) / sr + 1.0)
    stream.stop()
    stream.close()

    if not blocks:
        print("запись пустая")
        return 1
    audio = np.concatenate(blocks)
    rms = float(np.sqrt((audio.astype(np.float64) ** 2).mean()))
    peak = float(np.abs(audio).max())
    print(f"записано {len(audio) / SR:.2f} с, RMS={rms:.4f}, пик={peak:.3f}")
    if peak < 0.005:
        print("!! тишина — стерео микшер ничего не снял")
        return 1

    # режем фрагмент вокруг громкой части
    win = int(SR * 0.02)
    n = len(audio) // win
    frames = audio[:n * win].reshape(n, win)
    energy = np.sqrt((frames.astype(np.float64) ** 2).mean(axis=1))
    loud = np.where(energy > max(float(energy.max()) * 0.2, 0.004))[0]
    if not loud.size:
        print("!! нет громких участков")
        return 1
    seg = audio[max(0, (loud[0] - 5) * win):min(len(audio), (loud[-1] + 25) * win)]
    print(f"фрагмент: {len(seg) / SR:.2f} с")

    # --- движок ---
    proc = subprocess.Popen(
        [ENG, SCRIPT, f"--reference={REF}"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
        errors="replace", bufsize=1,
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})

    def send(msg: dict) -> None:
        proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
        proc.stdin.flush()

    try:
        send({"cmd": "load"})
        t0 = time.time()
        while time.time() - t0 < 240:
            line = proc.stdout.readline()
            if not line:
                break
            try:
                msg = json.loads(line)
            except Exception:
                continue
            if msg.get("event") == "ready":
                print(f"движок готов за {int((time.time() - t0) * 1000)} мс")
                break
        send({"cmd": "peer_lang", "code": "es"})

        # 16 кГц для Whisper
        from math import gcd
        from scipy.signal import resample_poly
        g = gcd(SR, 16000)
        seg16 = resample_poly(seg, 16000 // g, SR // g).astype(np.float32)
        pcm = (np.clip(seg16, -1.0, 1.0) * 32767).astype(np.int16)
        send({"cmd": "peer", "sr": 16000,
              "pcm": base64.b64encode(pcm.tobytes()).decode("ascii")})

        t0 = time.time()
        got = None
        while time.time() - t0 < 90:
            line = proc.stdout.readline()
            if not line:
                break
            try:
                msg = json.loads(line)
            except Exception:
                continue
            if msg.get("event") == "peer_text":
                got = msg
                break
        if not got:
            print("!! перехват не сработал")
            return 1
        print(f"перехват: {got.get('src')!r} -> {got.get('ru')!r}")
        return 0
    finally:
        try:
            send({"cmd": "quit"})
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
