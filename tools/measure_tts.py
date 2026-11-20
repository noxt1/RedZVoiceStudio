"""Замер задержки первого звука TTS на настоящем движке.

Поднимает `tools/live_translate.py` тем же способом, что приложение,
и шлёт ему команду `speak` — то есть меряет ровно тот путь, которым
перевод уходит в кабель: текст -> XTTS -> первый `chunk`.

Что показывает:
  * `wall_ms` — от отправки текста до первого куска звука;
  * `tts_first_ms` — то же по счётчику движка (в metrics);
  * `total_ms` — до события `done` (конец синтеза).

Сравнение «до/после» делается двумя прогонами в один json-файл:
    python tools/measure_tts.py --json out/tts_before.json
    ... правка ...
    python tools/measure_tts.py --json out/tts_after.json

Нужен установленный движок (`%LOCALAPPDATA%\\Auraloom\\engine`) и образец
голоса; звук никуда не выводится — только синтез в памяти.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

import studio_paths as sp  # noqa: E402

PHRASES = {
    "short": "Hola, amigo. ¿Cómo estás hoy?",
    "long": ("Hoy iremos al norte, allí hay un puente viejo, detrás empieza "
             "el bosque, y en el bosque vive un anciano que conoce el camino"),
}


def _reader(proc: subprocess.Popen, lines: "queue.Queue[str]") -> None:
    for line in proc.stdout:  # type: ignore[union-attr]
        lines.put(line.rstrip("\r\n"))
    lines.put("")


def _wait(lines: queue.Queue, name: str, timeout: float) -> dict | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            line = lines.get(timeout=0.5)
        except queue.Empty:
            continue
        if not line:
            return None
        if not line.startswith("{"):
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue
        if msg.get("event") == name:
            return msg
    return None


def _speak(proc, lines, text: str, seq: int) -> dict:
    """Отправить текст и дождаться первого chunk и done."""
    t0 = time.perf_counter()
    payload = json.dumps({"cmd": "speak", "text": text, "seq": seq})
    proc.stdin.write(payload + "\n")
    proc.stdin.flush()

    first_ms = None
    tts_first = None
    total_ms = None
    deadline = time.time() + 120
    while time.time() < deadline:
        try:
            raw = lines.get(timeout=0.5)
        except queue.Empty:
            continue
        if not raw:
            break
        if not raw.startswith("{"):
            continue
        try:
            msg = json.loads(raw)
        except Exception:
            continue
        event = msg.get("event")
        if event == "chunk" and first_ms is None:
            first_ms = int((time.perf_counter() - t0) * 1000)
        elif event == "metrics" and msg.get("dir") == "out_tts":
            tts_first = msg.get("tts_first_ms")
        elif event == "done":
            total_ms = int((time.perf_counter() - t0) * 1000)
            break
    return {"text": text, "wall_ms": first_ms, "tts_first_ms": tts_first,
            "total_ms": total_ms}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", default="", help="куда записать результат")
    parser.add_argument("--runs", type=int, default=3,
                        help="повторов на фразу (по умолчанию 3)")
    parser.add_argument("--mode", default="balanced",
                        help="режим движка: fast/balanced/quality/manual")
    parser.add_argument("--timeout", type=float, default=420.0,
                        help="сколько ждать загрузку моделей, с")
    args = parser.parse_args()

    python = sp.engine_python()
    if not python:
        print("движок не найден (нет engine\\Scripts\\python.exe)")
        return 2
    src_ref = os.path.join(sp.workspace(), "reference.wav")
    if not os.path.exists(src_ref):
        print(f"нет образца голоса: {src_ref}")
        return 2

    # Свой каталог: движок пишет рядом с reference свой лог, не трогаем
    # рабочий лог пользователя.
    probe = os.path.join(ROOT, "out", "tts_probe")
    os.makedirs(probe, exist_ok=True)
    reference = os.path.join(probe, "reference.wav")
    if not os.path.exists(reference) or (
            os.path.getsize(reference) != os.path.getsize(src_ref)):
        shutil.copyfile(src_ref, reference)

    cmd = [python, os.path.join(ROOT, "tools", "live_translate.py"),
           f"--reference={reference}"]
    print("запуск движка:", " ".join(cmd))
    proc = subprocess.Popen(cmd, cwd=ROOT, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            text=True, encoding="utf-8", bufsize=1)
    lines: "queue.Queue[str]" = queue.Queue()
    threading.Thread(target=_reader, args=(proc, lines), daemon=True).start()

    try:
        if _wait(lines, "boot", 30) is None:
            print("движок не ответил на старте")
            return 3
        proc.stdin.write(json.dumps({"cmd": "mode",
                                     "code": args.mode}) + "\n")
        proc.stdin.flush()
        proc.stdin.write(json.dumps({"cmd": "load"}) + "\n")
        proc.stdin.flush()
        print("жду загрузку моделей…")
        ready = _wait(lines, "ready", args.timeout)
        if ready is None:
            print("модели не загрузились за отведённое время")
            return 4
        print(f"модели загружены за {ready.get('load_ms', '?')} мс")

        rows = []
        seq = 0
        for kind, text in PHRASES.items():
            for run in range(max(1, args.runs)):
                seq += 1
                row = _speak(proc, lines, text, seq)
                row.update({"kind": kind, "run": run + 1, "mode": args.mode})
                rows.append(row)
                print(f"  {kind:<5} прогон {run + 1}: "
                      f"первый звук {row['wall_ms']} мс, "
                      f"конец {row['total_ms']} мс")
    finally:
        try:
            proc.stdin.write(json.dumps({"cmd": "quit"}) + "\n")
            proc.stdin.flush()
        except Exception:
            pass
        try:
            proc.wait(timeout=15)
        except Exception:
            proc.kill()

    warm = {}
    for kind in PHRASES:
        got = [r["wall_ms"] for r in rows
               if r["kind"] == kind and r["wall_ms"] is not None]
        if got:
            warm[kind] = {"min": min(got), "median": sorted(got)[len(got) // 2],
                          "max": max(got)}
    print("\nпервый звук, мс (без прогрева: первый прогон каждой фразы):")
    for kind, stats in warm.items():
        print(f"  {kind:<5} min {stats['min']}  медиана {stats['median']}"
              f"  max {stats['max']}")

    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"mode": args.mode, "rows": rows, "summary": warm},
                      fh, ensure_ascii=False, indent=2)
        print(f"  json: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
