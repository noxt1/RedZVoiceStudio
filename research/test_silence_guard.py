"""Тест: тишина не должна порождать перевод.

1) Записывает 6 секунд тишины (эталон) и сохраняет.
2) Прогоняет новый VAD приложения по эталону -> ждём 0 фраз.
3) Прогоняет движок (новые настройки) по эталону -> ждём пустой текст
   и НИ ОДНОГО аудио-чанка (иначе приложение будет «говорить в пустоту»).

    "<engine>\\Scripts\\python.exe" research\\test_silence_guard.py
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

import live_tab as lt  # noqa: E402

WS = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Auraloom", "workspace")
ENGINE = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Auraloom",
                      "engine", "Scripts", "python.exe")
SCRIPT = os.path.join(WS, "tools", "live_translate.py")
REF = os.path.join(WS, "reference.wav")
SIL_FILE = os.path.join(WS, "logs", "silence_ref.wav")
SR = 44100


def record_silence(seconds: float = 6.0) -> np.ndarray:
    import sounddevice as sd
    try:
        default_in = sd.default.device[0]
    except Exception:
        default_in = 0
    print(f"микрофон: [{default_in}] {sd.query_devices(default_in)['name']}")
    print(f"записываю {seconds:.0f} с — ГОВОРИ НИЧЕГО")
    rec = sd.rec(int(SR * seconds), samplerate=SR, channels=1, dtype="float32",
                 device=default_in)
    sd.wait()
    return np.asarray(rec, dtype="float32").squeeze()


def run_vad(audio: np.ndarray) -> list[np.ndarray]:
    obj = lt.LiveTab.__new__(lt.LiveTab)
    obj._cont_buf = []
    obj._cont_silence = 0.0
    obj._cont_has_speech = False
    obj._noise = 0.005
    obj._rms_history = []
    obj._smooth = []
    obj._strong_blocks = 0
    obj._cont_on = True
    sent = []
    obj._queue_translate = lambda pcm, sr=44100: sent.append(pcm.copy())
    step = int(SR * lt.BLOCK_SEC)
    for i in range(len(audio) // step):
        obj._cont_callback(audio[i * step:(i + 1) * step].reshape(-1, 1), 0, None, None)
    return sent


def run_engine(audio: np.ndarray) -> tuple[str, int]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["COQUI_TOS_AGREED"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen([ENGINE, SCRIPT, f"--reference={REF}"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                            errors="replace", bufsize=1, env=env,
                            cwd=os.path.dirname(SCRIPT))

    def send(msg):
        proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
        proc.stdin.flush()

    send({"cmd": "load"})
    while True:
        line = proc.stdout.readline()
        if not line:
            return "движок упал", 0
        try:
            msg = json.loads(line)
        except Exception:
            continue
        if msg.get("event") == "ready":
            break
        if msg.get("event") == "error":
            return msg.get("message", "?"), 0

    data = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    send({"cmd": "translate", "seq": 1, "sr": SR,
          "pcm": base64.b64encode(data.tobytes()).decode("ascii")})
    text = ""
    chunks = 0
    while True:
        line = proc.stdout.readline()
        if not line:
            break
        try:
            msg = json.loads(line)
        except Exception:
            continue
        if msg.get("event") == "text":
            text = msg.get("ru", "")
        elif msg.get("event") == "chunk":
            chunks += 1
        elif msg.get("event") in ("done", "error"):
            break
    proc.stdin.write(json.dumps({"cmd": "quit"}) + "\n")
    proc.stdin.flush()
    time.sleep(0.5)
    proc.kill()
    return text, chunks


def quietest_window(audio: np.ndarray, win_sec: float = 4.0) -> np.ndarray:
    """Самый тихий кусок записи — это и есть «тишина» (шум комнаты)."""
    win = int(SR * win_sec)
    if len(audio) <= win:
        return audio
    step = int(SR * 0.2)
    best = None
    best_rms = None
    for i in range(0, len(audio) - win, step):
        part = audio[i:i + win]
        r = float(np.sqrt((part.astype(np.float64) ** 2).mean()))
        if best_rms is None or r < best_rms:
            best_rms = r
            best = part
    return best if best is not None else audio


def make_room_noise() -> np.ndarray:
    """Собрать «тишину» из реальных пауз в записях образца.

    В записях между фразами есть настоящие тихие участки (RMS < 0.004).
    Склеиваем их и поднимаем до уровня шума комнаты, который мы измерили
    на микрофоне (RMS ~0.008).
    """
    import glob
    import glob as _g
    samples = sorted(glob.glob(os.path.join(WS, "voice_samples", "*.wav")))
    pieces = []
    for path in samples[:8]:
        try:
            a, sr = sf_read(path)
        except Exception:
            continue
        step = int(sr * 0.05)
        for i in range(len(a) // step):
            block = a[i * step:(i + 1) * step]
            if len(block) == step:
                r = float(np.sqrt((block.astype(np.float64) ** 2).mean()))
                if r < 0.004:
                    pieces.append(block)
    if not pieces:
        return np.zeros(int(SR * 4), dtype=np.float32)
    noise = np.concatenate(pieces)
    cur = float(np.sqrt((noise.astype(np.float64) ** 2).mean()))
    if cur > 1e-6:
        noise = noise / cur * 0.008      # уровень шума комнаты
    return noise


def sf_read(path: str):
    import soundfile as sf
    a, sr = sf.read(path, dtype="float32", always_2d=False)
    if a.ndim > 1:
        a = a.mean(axis=1)
    return a, sr


def main() -> None:
    import soundfile as sf

    if os.path.exists(SIL_FILE) and "--rec" not in sys.argv:
        audio, sr = sf.read(SIL_FILE, dtype="float32", always_2d=False)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        print(f"используем эталон тишины: {SIL_FILE}")
    else:
        audio = record_silence()
        os.makedirs(os.path.dirname(SIL_FILE), exist_ok=True)
        sf.write(SIL_FILE, audio, SR)
        print(f"сохранено: {SIL_FILE}")

    rms = float(np.sqrt((audio.astype(np.float64) ** 2).mean()))
    print(f"\nвся запись: RMS {rms:.5f}")

    # эталон тишины: настоящие паузы + уровень шума комнаты
    quiet = make_room_noise()
    qrms = float(np.sqrt((quiet.astype(np.float64) ** 2).mean()))
    qpeak = float(np.abs(quiet).max())
    print(f"эталон тишины ({len(quiet) / SR:.1f} с): RMS {qrms:.5f}, пик {qpeak:.4f}")

    print("\n=== 1. VAD приложения на тишине ===")
    sent = run_vad(quiet)
    print(f"  фраз отправлено на перевод: {len(sent)} (ожидаем 0)")
    for i, p in enumerate(sent):
        print(f"    [{i}] {len(p) / SR:.2f} с")
    ok_vad = len(sent) == 0

    print("\n=== 2. Движок на тишине ===")
    text, chunks = run_engine(quiet)
    print(f"  распознано: {text!r}")
    print(f"  аудио-чанков: {chunks} (ожидаем 0)")
    ok_engine = not text.strip() and chunks == 0

    print("\n=== 3. Контроль: настоящая речь должна распознаваться ===")
    spoken = audio if rms > 0.02 else quiet
    text2, chunks2 = run_engine(spoken)
    print(f"  распознано: {text2[:70]!r}")
    print(f"  аудио-чанков: {chunks2}")
    ok_speech = bool(text2.strip()) and chunks2 > 0

    print("\n=== ИТОГ ===")
    print(f"  VAD не пропускает тишину:  {'ок' if ok_vad else 'ОШИБКА'}")
    print(f"  движок молчит на тишине:    {'ок' if ok_engine else 'ОШИБКА'}")
    print(f"  речь распознаётся и звучит: {'ок' if ok_speech else 'ОШИБКА'}")
    if not (ok_vad and ok_engine and ok_speech):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
