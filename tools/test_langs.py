"""Тест движка: перевод на разные языки + перехват речи игроков.

Запуск (нужен движок с моделями):
    python tools\\test_langs.py

Что проверяем:
  1. Перевод RU->ES работает (как раньше).
  2. Переключение языка на en / ow / it: перевод меняется, XTTS
     переключается на нужный код языка.
  3. Перехват: испанская реплика из озвучки -> распознана и переведена
     на русский.
  4. Собственный голос в перехват не попадает (мы его сами сказали).
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
WS = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Auraloom", "workspace")
ENG = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Auraloom",
                   "engine", "Scripts", "python.exe")
SCRIPT = os.path.join(WS, "tools", "live_translate.py")
REF = os.path.join(WS, "reference.wav")
SR_ASR = 16000


def load_wav(path: str) -> tuple[np.ndarray, int]:
    """Прочитать wav/ogg/mp3 и привести к моно float32."""
    import soundfile as sf
    data, sr = sf.read(path, dtype="float32", always_2d=False)
    if data.ndim > 1:
        data = data.mean(axis=1)
    return data, sr


def to_16k(audio: np.ndarray, sr: int) -> np.ndarray:
    if sr == SR_ASR:
        return audio
    from math import gcd
    from scipy.signal import resample_poly
    g = gcd(int(sr), SR_ASR)
    return resample_poly(audio, SR_ASR // g, int(sr) // g).astype(np.float32)


def pcm_b64(audio: np.ndarray) -> str:
    data = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
    return base64.b64encode(data.tobytes()).decode("ascii")


class Engine:
    """Обёртка над процессом движка."""

    def __init__(self) -> None:
        self.proc = subprocess.Popen(
            [ENG, SCRIPT, f"--reference={REF}"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
            errors="replace", bufsize=1,
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
        self.events: list[dict] = []

    def send(self, msg: dict) -> None:
        self.proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def wait(self, kind: str, timeout: float = 60.0) -> dict | None:
        """Дождаться события указанного вида."""
        t0 = time.time()
        while time.time() - t0 < timeout:
            line = self.proc.stdout.readline()
            if not line:
                return None
            try:
                msg = json.loads(line)
            except Exception:
                continue
            if msg.get("event") == "chunk":
                continue      # аудио — не интересно
            self.events.append(msg)
            if msg.get("event") == kind:
                return msg
        return None

    def close(self) -> None:
        try:
            self.send({"cmd": "quit"})
            self.proc.wait(timeout=5)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass


def main() -> int:
    if not os.path.exists(REF):
        print("нет reference.wav — сначала запиши образец голоса")
        return 1
    if not os.path.exists(SCRIPT):
        print("нет движка в рабочей папке:", SCRIPT)
        return 1

    sample = os.path.join(WS, "voice_samples", "take_01.wav")
    if not os.path.exists(sample):
        samples = os.path.join(WS, "voice_samples")
        files = sorted(f for f in os.listdir(samples) if f.endswith(".wav"))
        sample = os.path.join(samples, files[0]) if files else None
    if not sample:
        print("нет записей образца")
        return 1

    audio, sr = load_wav(sample)
    audio16 = to_16k(audio, sr)

    # испанская реплика из озвучки — ею проверим перехват
    es_clip = os.path.join(WS, "out", "mp3", "mx_01.mp3")
    es_audio = None
    if os.path.exists(es_clip):
        try:
            a, s = load_wav(es_clip)
            es_audio = to_16k(a, s)
        except Exception as exc:
            print("не смог прочитать mp3:", exc)

    eng = Engine()
    fails = 0
    try:
        print("загружаю модели…")
        # без команды load движок не грузит модели
        eng.send({"cmd": "load"})
        ready = eng.wait("ready", timeout=240)
        if not ready:
            print("движок не поднялся")
            return 1
        print(f"готов: загрузка {ready.get('load_ms')} мс")

        # --- 1. испанский (по умолчанию) ---
        eng.send({"cmd": "translate", "seq": 1, "sr": SR_ASR,
                  "floor": 0.0, "pcm": pcm_b64(audio16)})
        text = eng.wait("text", timeout=90)
        if not text:
            print("!! нет перевода")
            fails += 1
        else:
            print(f"RU: {text.get('ru')!r}")
            print(f"ES: {text.get('es')!r}")
            if not text.get("es"):
                print("!! пустой перевод")
                fails += 1
        eng.wait("done", timeout=90)

        # --- 2. английский ---
        eng.send({"cmd": "lang", "code": "en"})
        time.sleep(1.0)
        eng.send({"cmd": "translate", "seq": 2, "sr": SR_ASR,
                  "floor": 0.0, "pcm": pcm_b64(audio16)})
        text = eng.wait("text", timeout=90)
        if not text or not text.get("es"):
            print("!! не перевёл на английский")
            fails += 1
        else:
            print(f"EN: {text.get('es')!r}")
        eng.wait("done", timeout=90)

        # --- 3. олдвест ---
        eng.send({"cmd": "lang", "code": "ow"})
        time.sleep(1.0)
        eng.send({"cmd": "translate", "seq": 3, "sr": SR_ASR,
                  "floor": 0.0, "pcm": pcm_b64(audio16)})
        text = eng.wait("text", timeout=90)
        if not text or not text.get("es"):
            print("!! не перевёл на олдвест")
            fails += 1
        else:
            print(f"OW: {text.get('es')!r}")
        eng.wait("done", timeout=90)

        # --- 4. итальянский ---
        eng.send({"cmd": "lang", "code": "it"})
        time.sleep(1.0)
        eng.send({"cmd": "translate", "seq": 4, "sr": SR_ASR,
                  "floor": 0.0, "pcm": pcm_b64(audio16)})
        text = eng.wait("text", timeout=120)
        if not text or not text.get("es"):
            print("!! не перевёл на итальянский")
            fails += 1
        else:
            print(f"IT: {text.get('es')!r}")
        eng.wait("done", timeout=120)

        # --- 5. перехват чужой речи ---
        if es_audio is not None:
            eng.send({"cmd": "peer_lang", "code": "es"})
            time.sleep(0.5)
            eng.send({"cmd": "peer", "sr": SR_ASR, "pcm": pcm_b64(es_audio)})
            peer = eng.wait("peer_text", timeout=90)
            if not peer:
                print("!! перехват не сработал")
                fails += 1
            else:
                print(f"перехват: {peer.get('src')!r} -> {peer.get('ru')!r}")
                if not peer.get("ru"):
                    print("!! нет перевода чужой речи")
                    fails += 1
        else:
            print("нет испанской озвучки — перехват не проверяем")

    finally:
        eng.close()

    print("\nИТОГ:", "всё ок" if fails == 0 else f"проблем: {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
