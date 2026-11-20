"""Сквозная проверка аудиопути без микрофона, Discord и второго человека.

Проверяются ровно те места, где ломался звук:
  * длинный перевод приходит пачкой кусков и должен дойти до кабеля целиком;
  * русский заглушён, пока включена заглушка, и возвращается после неё;
  * `clear_stream()` убирает недозвучавшее, а не оставляет его в наушниках;
  * предел очереди не даёт копить минуты, а переполнение считается.

Устройства не открываются: блоки «микрофона» и «выходного колбэка»
подаются вручную, поэтому скрипт работает на машине без кабеля, наушников
и звуковой карты.

Запуск:
    python tools/live_path_check.py
    python tools/live_path_check.py --json out/live_path.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(ROOT, "app") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "app"))

import mic_bridge  # noqa: E402

SR = 48000
CHUNK_SEC = 0.5          # так движок отдаёт перевод: куски по ~0,5 с @24 кГц
TTS_SR = 24000


def make_bridge(mic_gain: float = 0.0, monitor: int | None = None):
    """Мост без открытия устройств (частота подставлена)."""
    old = mic_bridge.pick_sample_rate
    mic_bridge.pick_sample_rate = lambda *a, **k: SR
    try:
        return mic_bridge.MicBridge(
            mic_device=None, render_device=None, mic_gain=mic_gain,
            monitor_device=monitor, monitor_gain=1.0)
    finally:
        mic_bridge.pick_sample_rate = old


def _run(bridge, seconds: float, mic_level: float | None = None) -> np.ndarray:
    """Прогнать N секунд в реальном темпе: блок микрофона + блок выхода.

    Подавать микрофон пачкой нельзя — у моста буфер на 16 блоков (~0,34 с),
    он рассчитан на поток. Поэтому на каждый блок выхода — один блок входа.
    """
    block = mic_bridge.BLOCK
    out = np.zeros((block, 1), dtype=np.float32)
    mic = np.zeros((block, 1), dtype=np.float32)
    if mic_level is not None:
        mic[:] = float(mic_level)
    chunks = []
    for _ in range(int(round(seconds * SR / block))):
        if mic_level is not None:
            bridge._in_callback(mic, block, None, None)
        bridge._mix_out(out, block)
        chunks.append(out[:, 0].copy())
    return np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)


def _push_translation(bridge, seconds: float, value: float = 0.5) -> None:
    """Отдать перевод так, как это делает движок: пачкой кусков."""
    n = int(CHUNK_SEC * TTS_SR)
    for _ in range(int(round(seconds / CHUNK_SEC))):
        bridge.push_pcm(np.full(n, value, dtype=np.float32), TTS_SR)


def check_queue_no_loss() -> dict:
    """10 секунд перевода, отданные пачкой, доходят целиком."""
    bridge = make_bridge(mic_gain=0.0)
    seconds = 10.0
    _push_translation(bridge, seconds)
    played = _run(bridge, seconds + 0.5)
    audible = int((np.abs(played) > 0.05).sum())
    expected = int(seconds * SR)
    ok = (audible == expected and bridge.stream_dropped == 0
          and not bridge.stream_pending())
    return {"check": "queue_no_loss", "ok": bool(ok),
            "expected_samples": expected, "audible_samples": audible,
            "dropped_chunks": bridge.stream_dropped,
            "dropped_sec": round(bridge.stream_dropped_sec, 3)}


def check_mic_plus_translation() -> dict:
    """Речь и перевод складываются без клиппинга и NaN."""
    bridge = make_bridge(mic_gain=1.0)
    bridge.set_duck(False)
    _push_translation(bridge, 3.0, value=0.4)
    played = _run(bridge, 3.5, mic_level=0.4)
    peak = float(np.abs(played).max()) if played.size else 0.0
    ok = bool(np.isfinite(played).all() and peak <= 1.0 and peak > 0.5)
    return {"check": "mic_plus_translation", "ok": ok,
            "peak": round(peak, 3)}


def check_duck_holds() -> dict:
    """Пока включена заглушка, русского в кабеле нет; после — есть."""
    bridge = make_bridge(mic_gain=1.0)
    bridge.set_duck(True)
    muted = _run(bridge, 1.0, mic_level=0.2)
    muted_peak = float(np.abs(muted).max()) if muted.size else 0.0

    bridge.set_duck(False)
    _run(bridge, 0.3, mic_level=0.2)          # нарастание
    restored = _run(bridge, 1.0, mic_level=0.2)
    restored_peak = float(np.abs(restored).max()) if restored.size else 0.0
    ok = muted_peak < 1e-4 and abs(restored_peak - 0.2) < 0.02
    return {"check": "duck_holds", "ok": bool(ok),
            "muted_peak": round(muted_peak, 6),
            "restored_peak": round(restored_peak, 4)}


def check_clear_stream() -> dict:
    """После отмены перевода в очереди и наушниках пусто."""
    bridge = make_bridge(mic_gain=0.0, monitor=1)
    _push_translation(bridge, 2.0)
    bridge.clear_stream()
    played = _run(bridge, 0.5)
    peak = float(np.abs(played).max()) if played.size else 0.0
    mon_peak = float(np.abs(np.concatenate(list(bridge._mon_q))).max()) \
        if bridge._mon_q else 0.0
    ok = (peak == 0.0 and mon_peak == 0.0
          and not bridge.stream_pending() and bridge._mon_len == 0)
    return {"check": "clear_stream", "ok": bool(ok),
            "cable_peak": round(peak, 6), "monitor_peak": round(mon_peak, 6)}


def check_queue_cap() -> dict:
    """Больше STREAM_MAX_SEC в очереди не копится, потерянное считается."""
    bridge = make_bridge(mic_gain=0.0)
    _push_translation(bridge, mic_bridge.STREAM_MAX_SEC + 10.0)
    queued_sec = bridge._stream_len / bridge.sr
    ok = (queued_sec <= mic_bridge.STREAM_MAX_SEC + 0.01
          and bridge.stream_dropped > 0
          and 5.0 <= bridge.stream_dropped_sec <= 12.0)
    return {"check": "queue_cap", "ok": bool(ok),
            "queued_sec": round(queued_sec, 2),
            "cap_sec": mic_bridge.STREAM_MAX_SEC,
            "dropped_sec": round(bridge.stream_dropped_sec, 2)}


CHECKS = (check_queue_no_loss, check_mic_plus_translation, check_duck_holds,
          check_clear_stream, check_queue_cap)


def run_checks() -> list[dict]:
    """Все проверки; каждая возвращает dict с ключом ok."""
    return [check() for check in CHECKS]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", default="", help="куда записать результат")
    args = parser.parse_args()

    results = run_checks()
    width = max(len(r["check"]) for r in results)
    print("\nАудиопуть без устройств")
    print("-" * (width + 34))
    for r in results:
        mark = "PASS" if r["ok"] else "FAIL"
        extra = "  ".join(
            f"{k}={v}" for k, v in r.items() if k not in ("check", "ok"))
        print(f"  {mark}  {r['check']:<{width}}  {extra}")
    failed = [r for r in results if not r["ok"]]
    print("-" * (width + 34))
    print(f"  итог: {len(results) - len(failed)}/{len(results)} PASS\n")

    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"results": results}, fh, ensure_ascii=False, indent=2)
        print(f"  json: {args.json}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
