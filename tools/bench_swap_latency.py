"""Замер: реальная задержка перевода (от отправки аудио до первого звука).

Меряет полный путь:
    аудио в движок -> распознавание (Whisper) -> перевод (opus-mt)
    -> синтез (XTTS) -> первый чанк аудио

Движок поднимается отдельно (как в приложении), аудио берётся из реальных
записей пользователя (workspace/voice_samples).

    python tools\\bench_swap_latency.py
"""

from __future__ import annotations

import glob
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

import live_client as lc  # noqa: E402
import studio_paths as sp  # noqa: E402


def main() -> None:
    ws = sp.workspace()
    ref = sp.output_paths()["reference"]
    script = os.path.join(sp.workspace_tools(), "live_translate.py")
    samples = sorted(glob.glob(os.path.join(ws, "voice_samples", "*.wav")))

    if not os.path.exists(ref):
        print(f"нет образца голоса: {ref}")
        return
    if not samples:
        print("нет записей для замера")
        return

    import soundfile as sf

    print("=== запуск движка ===")
    marks: dict[str, float] = {}
    t0_start = time.time()

    def on_event(kind: str, data) -> None:
        if kind == "text":
            marks["text"] = time.time()
        elif kind == "chunk":
            marks.setdefault("chunk", time.time())
        elif kind == "done":
            marks.setdefault("done", time.time())

    t = lc.LiveTranslator(sp.engine_python(), script, ref, on_event=on_event)
    if not t.start():
        print(f"движок не запустился: {t.error}")
        return

    deadline = time.time() + 240
    while not t.ready and time.time() < deadline:
        t.poll()
        time.sleep(0.5)
    if not t.ready:
        print("движок не загрузил модели за 240 с")
        t.stop()
        return
    print(f"  движок готов за {time.time() - t0_start:.0f} с\n")

    print("=== замер: аудио -> первый звук перевода ===")
    results = []
    for path in samples[:4]:
        audio, sr = sf.read(path, dtype="float32", always_2d=False)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        dur = len(audio) / sr

        marks.clear()
        t0 = time.time()
        if not t.translate_pcm(audio, sr, floor=0.0):
            print("  движок занят — пропуск")
            time.sleep(2)
            continue

        deadline = time.time() + 40
        while time.time() < deadline:
            t.poll()
            if "chunk" in marks:
                break
            time.sleep(0.005)

        if "chunk" not in marks:
            print(f"  {os.path.basename(path)}: нет ответа за 40 с")
            continue
        to_text = (marks["text"] - t0) * 1000 if "text" in marks else float("nan")
        to_chunk = (marks["chunk"] - t0) * 1000
        print(f"  {os.path.basename(path):<14} ({dur:.1f} с)  "
              f"текст {to_text:6.0f} мс | первый звук {to_chunk:6.0f} мс")
        results.append(to_chunk)

        # ждём завершения, чтобы движок освободился
        deadline = time.time() + 40
        while time.time() < deadline and t.busy:
            t.poll()
            time.sleep(0.02)

    t.stop()
    if results:
        print(f"\n  среднее до первого звука: {np.mean(results):.0f} мс")
        print(f"  максимум: {np.max(results):.0f} мс")


if __name__ == "__main__":
    main()
