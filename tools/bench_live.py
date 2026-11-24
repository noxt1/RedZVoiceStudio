"""Замеры аудиопути: запас по времени и soak без утечек.

Что меряется (без устройств, без моделей — только код моста):
  * `mix`      — сколько секунд звука микшер успевает за секунду CPU;
  * `monitor`  — то же для шины наушников;
  * `push`     — стоимость приёма куска перевода (0,5 с @24 кГц);
  * `resample` — перевод 24 кГц → частота кабеля;
  * `soak`     — 30 минут звука с пачками перевода: очередь не растёт,
                 потерянных секунд нет, RSS не ползёт.

Зачем: оптимизации (стриминговый синтез, буферы) нужно подтверждать
числами, а не на слух. Бюджет аудиоколбэка при блоке 1024 @48 кГц —
21,33 мс; всё, что ниже, — запас.

Запуск:
    python tools/bench_live.py
    python tools/bench_live.py --quick --soak 5
    python tools/bench_live.py --json out/bench.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(ROOT, "app") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "app"))

import mic_bridge  # noqa: E402

SR = mic_bridge.BLOCK * 1000 // 21  # ~48780, оставляем 48000
SR = 48000
TTS_SR = 24000
BUDGET_US = mic_bridge.BLOCK / SR * 1e6      # 21,33 мс
CHUNK_SEC = 0.5


def make_bridge(monitor: int | None = None):
    old = mic_bridge.pick_sample_rate
    mic_bridge.pick_sample_rate = lambda *a, **k: SR
    try:
        return mic_bridge.MicBridge(
            mic_device=None, render_device=None, mic_gain=0.0,
            monitor_device=monitor, monitor_gain=1.0)
    finally:
        mic_bridge.pick_sample_rate = old


def _push_seconds(bridge, seconds: float) -> None:
    chunk = np.full(int(CHUNK_SEC * TTS_SR), 0.3, dtype=np.float32)
    for _ in range(int(round(seconds / CHUNK_SEC))):
        bridge.push_pcm(chunk, TTS_SR)


def bench_mix(seconds: float) -> dict:
    """Микшер кабеля: реальное время против CPU."""
    bridge = make_bridge()
    _push_seconds(bridge, seconds)
    out = np.zeros((mic_bridge.BLOCK, 1), dtype=np.float32)
    mic = np.zeros((mic_bridge.BLOCK, 1), dtype=np.float32)
    blocks = int(seconds * SR / mic_bridge.BLOCK)
    t0 = time.perf_counter()
    for _ in range(blocks):
        bridge._in_callback(mic, mic_bridge.BLOCK, None, None)
        bridge._mix_out(out, mic_bridge.BLOCK)
    wall = time.perf_counter() - t0
    return {"case": "mix", "audio_sec": round(seconds, 1),
            "wall_ms": round(wall * 1000, 1),
            "realtime_x": round(seconds / wall, 1) if wall else None,
            "per_block_us": round(wall / max(1, blocks) * 1e6, 1),
            "budget_us": round(BUDGET_US, 1)}


def bench_monitor(seconds: float) -> dict:
    """Шина наушников (второй поток, дублирует перевод)."""
    bridge = make_bridge(monitor=1)
    bridge._mon_sr = SR
    _push_seconds(bridge, seconds)
    out = np.zeros((mic_bridge.BLOCK, 1), dtype=np.float32)
    blocks = int(seconds * SR / mic_bridge.BLOCK)
    t0 = time.perf_counter()
    for _ in range(blocks):
        bridge._mix_mon(out)
    wall = time.perf_counter() - t0
    return {"case": "monitor", "audio_sec": round(seconds, 1),
            "wall_ms": round(wall * 1000, 1),
            "realtime_x": round(seconds / wall, 1) if wall else None,
            "per_block_us": round(wall / max(1, blocks) * 1e6, 1),
            "budget_us": round(BUDGET_US, 1)}


def bench_push(seconds: float) -> dict:
    """Приём куска 0,5 с от движка (ресемплинг + лимит очереди)."""
    bridge = make_bridge()
    chunk = np.full(int(CHUNK_SEC * TTS_SR), 0.3, dtype=np.float32)
    count = int(round(seconds / CHUNK_SEC))
    t0 = time.perf_counter()
    for _ in range(count):
        bridge.push_pcm(chunk, TTS_SR)
    wall = time.perf_counter() - t0
    return {"case": "push", "audio_sec": round(count * CHUNK_SEC, 1),
            "wall_ms": round(wall * 1000, 1),
            "realtime_x": round(count * CHUNK_SEC / wall, 1) if wall else None,
            "per_block_us": round(wall / max(1, count) * 1e6, 1),
            "budget_us": round(BUDGET_US, 1)}


def bench_resample(seconds: float) -> dict:
    """24 кГц → 48 кГц (линейная интерполяция)."""
    data = np.full(int(CHUNK_SEC * TTS_SR), 0.3, dtype=np.float32)
    count = int(round(seconds / CHUNK_SEC))
    t0 = time.perf_counter()
    for _ in range(count):
        mic_bridge.MicBridge._resample(data, TTS_SR, SR)
    wall = time.perf_counter() - t0
    return {"case": "resample", "audio_sec": round(count * CHUNK_SEC, 1),
            "wall_ms": round(wall * 1000, 1),
            "realtime_x": round(count * CHUNK_SEC / wall, 1) if wall else None,
            "per_block_us": round(wall / max(1, count) * 1e6, 1),
            "budget_us": round(BUDGET_US, 1)}


def _rss_mb() -> float | None:
    """Память процесса: psutil, иначе WinAPI (psutil есть не везде)."""
    try:
        import psutil
        return round(psutil.Process().memory_info().rss / (1024 * 1024), 1)
    except Exception:
        pass
    try:
        import ctypes
        import ctypes.wintypes as wt

        class PMC(ctypes.Structure):
            _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t)]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = wt.HANDLE
        get_info = kernel.K32GetProcessMemoryInfo
        get_info.argtypes = [wt.HANDLE, ctypes.POINTER(PMC), wt.DWORD]
        get_info.restype = wt.BOOL
        counter = PMC()
        counter.cb = ctypes.sizeof(counter)
        if not get_info(kernel.GetCurrentProcess(), ctypes.byref(counter),
                        counter.cb):
            return None
        return round(counter.WorkingSetSize / (1024 * 1024), 1)
    except Exception:
        return None


def soak(minutes: float) -> dict:
    """Длительная сессия: пачка перевода раз в 4 с + микрофон/выход."""
    bridge = make_bridge(monitor=1)
    bridge._mon_sr = SR
    out = np.zeros((mic_bridge.BLOCK, 1), dtype=np.float32)
    mic = np.zeros((mic_bridge.BLOCK, 1), dtype=np.float32)
    chunk = np.full(int(CHUNK_SEC * TTS_SR), 0.3, dtype=np.float32)

    total_sec = minutes * 60.0
    rss0 = _rss_mb()
    max_queue_sec = 0.0
    pushes = 0
    # реальное время не ждём: гоняем блоки так быстро, как успевает CPU
    next_push = 0.0
    t = 0.0
    block_sec = mic_bridge.BLOCK / SR
    while t < total_sec:
        if t >= next_push:
            for _ in range(6):                 # фраза 3 с пачкой кусков
                bridge.push_pcm(chunk, TTS_SR)
            pushes += 1
            next_push += 4.0
        bridge._in_callback(mic, mic_bridge.BLOCK, None, None)
        bridge._mix_out(out, mic_bridge.BLOCK)
        bridge._mix_mon(out)
        t += block_sec
        max_queue_sec = max(max_queue_sec, bridge._stream_len / bridge.sr)

    rss1 = _rss_mb()
    ok = (bridge.stream_dropped == 0
          and max_queue_sec <= mic_bridge.STREAM_MAX_SEC * 0.75
          and (rss0 is None or rss1 is None or rss1 - rss0 < 120))
    return {"case": "soak", "minutes": minutes, "pushes": pushes,
            "dropped_chunks": bridge.stream_dropped,
            "dropped_sec": round(bridge.stream_dropped_sec, 3),
            "max_queue_sec": round(max_queue_sec, 2),
            "rss_mb_start": rss0, "rss_mb_end": rss1,
            "ok": bool(ok)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true",
                        help="короче: 10 с микшера вместо 60")
    parser.add_argument("--soak", type=float, default=30.0,
                        help="минут звука для soak (по умолчанию 30)")
    parser.add_argument("--json", default="", help="куда записать результат")
    args = parser.parse_args()

    span = 10.0 if args.quick else 60.0
    results = [bench_mix(span), bench_monitor(span),
               bench_push(span), bench_resample(span), soak(args.soak)]

    print("\nАудиопульт: запас по времени (бюджет блока "
          f"{BUDGET_US:.1f} мкс)")
    print("-" * 92)
    print(f"  {'случай':<10}{'звук, с':>9}{'CPU, мс':>10}"
          f"{'x раз быстрее реального':>24}{'мкс на блок':>14}")
    for r in results:
        if r["case"] == "soak":
            continue
        print(f"  {r['case']:<10}{r['audio_sec']:>9.1f}{r['wall_ms']:>10.1f}"
              f"{r['realtime_x']:>24.1f}{r['per_block_us']:>14.1f}")
    s = results[-1]
    print("-" * 92)
    print(f"  soak {s['minutes']:.0f} мин: пачек {s['pushes']}, "
          f"очередь ≤ {s['max_queue_sec']:.2f} с, "
          f"потеряно {s['dropped_sec']:.2f} с, "
          f"RSS {s['rss_mb_start']} → {s['rss_mb_end']} МБ — "
          f"{'PASS' if s['ok'] else 'FAIL'}")
    print()

    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"results": results,
                       "block_budget_us": BUDGET_US},
                      fh, ensure_ascii=False, indent=2)
        print(f"  json: {args.json}")
    return 0 if s["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
