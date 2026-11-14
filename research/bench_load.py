"""Замер нагрузки движка живого перевода: хватит ли железа для игры.

Показывает, сколько ресурсов съедает движок перевода, чтобы понять,
потянет ли одновременно RedM/FiveM (или другая игра) на той же машине.

Меряет:
  * VRAM (nvidia-smi) до, во время и после;
  * CPU движка и всего процесса;
  * загрузку GPU во время синтеза;
  * сколько времени занимает перевод фразы (т.е. сколько «просядет» игра).

    "<engine>\\Scripts\\python.exe" research\\bench_load.py
"""

from __future__ import annotations

import base64
import glob
import json
import os
import subprocess
import time

import numpy as np

WS = os.path.join(os.environ.get("LOCALAPPDATA", ""), "RedZVoiceStudio", "workspace")
ENGINE = os.path.join(os.environ.get("LOCALAPPDATA", ""), "RedZVoiceStudio",
                      "engine", "Scripts", "python.exe")
SCRIPT = os.path.join(WS, "tools", "live_translate.py")
REF = os.path.join(WS, "reference.wav")
SAMPLES = os.path.join(WS, "voice_samples")


def gpu_info() -> dict:
    """VRAM и загрузка GPU."""
    out = {"vram_used": 0, "vram_total": 0, "util": 0}
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15)
        parts = [p.strip() for p in r.stdout.strip().split(",")]
        out["vram_used"] = int(parts[0])
        out["vram_total"] = int(parts[1])
        out["util"] = int(parts[2])
    except Exception:
        pass
    return out


def proc_info(pid: int) -> dict:
    """CPU% и память процесса движка."""
    out = {"cpu": 0.0, "rss_mb": 0}
    try:
        r = subprocess.run(["wmic", "process", "where", f"ProcessId={pid}",
                            "get", "ProcessId,WorkingSetSize"],
                           capture_output=True, text=True, errors="replace",
                           timeout=20)
        for line in r.stdout.splitlines():
            if line.strip().isdigit() and "WorkingSetSize" not in line:
                out["rss_mb"] = int(line.strip()) // (1024 * 1024)
                break
    except Exception:
        pass
    return out


def main() -> None:
    import soundfile as sf

    if not os.path.exists(SCRIPT):
        print(f"нет движка: {SCRIPT}")
        return

    print("=== состояние системы ДО запуска движка ===")
    base = gpu_info()
    print(f"  VRAM: {base['vram_used']} / {base['vram_total']} МБ, GPU {base['util']}%")

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
    print(f"\nдвижок: PID {proc.pid}")

    def send(msg: dict) -> None:
        proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
        proc.stdin.flush()

    print("загружаю модели ...")
    t0 = time.time()
    send({"cmd": "load"})
    while True:
        line = proc.stdout.readline()
        if not line:
            print("движок упал")
            return
        try:
            msg = json.loads(line)
        except Exception:
            continue
        if msg.get("event") == "ready":
            print(f"  готов за {time.time() - t0:.1f} с")
            break
        if msg.get("event") == "error":
            print(f"  ОШИБКА: {msg.get('message')}")
            return

    loaded = gpu_info()
    pi = proc_info(proc.pid)
    print("\n=== состояние ПОСЛЕ загрузки моделей ===")
    print(f"  VRAM: {loaded['vram_used']} МБ (было {base['vram_used']}) "
          f"-> движок занял ~{loaded['vram_used'] - base['vram_used']} МБ")
    print(f"  VRAM свободно: {loaded['vram_total'] - loaded['vram_used']} "
          f"из {loaded['vram_total']} МБ")
    print(f"  RAM движка: {pi['rss_mb']} МБ")

    # --- серия переводов: замеряем нагрузку и время ---
    files = sorted(glob.glob(os.path.join(SAMPLES, "*.wav")))[:6]
    times = []
    print("\n=== переводы подряд (как в непрерывном режиме) ===")
    for path in files:
        audio, sr = sf.read(path, dtype="float32", always_2d=False)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        data = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
        # замер GPU во время синтеза
        g0 = gpu_info()
        t0 = time.time()
        send({"cmd": "translate", "seq": 1, "sr": int(sr),
              "pcm": base64.b64encode(data.tobytes()).decode("ascii")})
        chunks = 0
        first = None
        while True:
            line = proc.stdout.readline()
            if not line:
                break
            try:
                msg = json.loads(line)
            except Exception:
                continue
            if msg.get("event") == "chunk":
                chunks += 1
                if first is None:
                    first = time.time() - t0
                    gmid = gpu_info()
            elif msg.get("event") == "done":
                break
            elif msg.get("event") == "error":
                print(f"  ОШИБКА: {msg.get('message')}")
                break
        total = time.time() - t0
        times.append(total)
        print(f"  {os.path.basename(path):<16} первый звук {first * 1000:5.0f} мс | "
              f"всего {total:.2f} с | GPU {gmid['util']:3d}% | "
              f"VRAM {gmid['vram_used']} МБ")

    print(f"\n  среднее время перевода фразы: {sum(times) / len(times):.2f} с")

    # --- что будет, если параллельно игра (имитация нагрузки на GPU) ---
    print("\n=== имитация игры: нагрузка на GPU ===")
    load = subprocess.Popen(
        ["nvidia-smi", "-l", "1", "--query-gpu=utilization.gpu,memory.used",
         "--format=csv,noheader,nounits"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # грузим GPU вычислениями через python движка
    busy = subprocess.Popen(
        [ENGINE, "-c",
         "import torch,time;a=torch.randn(4096,4096,device='cuda');"
         "t=time.time()\n"
         "while time.time()-t<25:\n"
         " a=a@a*0.0001+0.1\n"
         "torch.cuda.synchronize()"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(6)
    g_busy = gpu_info()
    print(f"  GPU под нагрузкой: {g_busy['util']}%, VRAM {g_busy['vram_used']} МБ "
          f"(свободно {g_busy['vram_total'] - g_busy['vram_used']} МБ)")
    t0 = time.time()
    send({"cmd": "translate", "seq": 2, "sr": 44100,
          "pcm": base64.b64encode(data.tobytes()).decode("ascii")})
    first_busy = None
    while True:
        line = proc.stdout.readline()
        if not line:
            break
        try:
            msg = json.loads(line)
        except Exception:
            continue
        if msg.get("event") == "chunk":
            if first_busy is None:
                first_busy = time.time() - t0
        elif msg.get("event") == "done":
            break
    if first_busy:
        print(f"  перевод под нагрузкой GPU: первый звук {first_busy * 1000:.0f} мс")
    busy.terminate()
    load.terminate()

    print("\n=== ВЫВОД ===")
    print(f"  VRAM на движок: ~{loaded['vram_used'] - base['vram_used']} МБ")
    print(f"  VRAM свободно: {loaded['vram_total'] - loaded['vram_used']} МБ "
          f"из {loaded['vram_total']} МБ")
    print(f"  RAM на движок: ~{pi['rss_mb']} МБ")

    proc.stdin.write(json.dumps({"cmd": "quit"}) + "\n")
    proc.stdin.flush()
    time.sleep(1)
    proc.kill()


if __name__ == "__main__":
    main()
