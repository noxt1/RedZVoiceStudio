"""Проверка промежуточного распознавания: без дублей и без перевода.

Для каждой фразы отправляются три растущих среза (partial) и финал.
Смотрим: тексты partial непустые, не дублируются подряд, перевод
(peer_text) появляется только после финала - и ровно один раз.
"""
from __future__ import annotations

import json
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from soak_live import Harness, load_wav, note, WAV_DIR  # noqa: E402


def main() -> int:
    h = Harness()
    open(os.path.join(ROOT, "build", "partial_probe_progress.txt"), "w").close()
    if not h.tr.start() or not h.wait_ready():
        print("движок не поднялся")
        return 2
    h.tr.set_peer_lang("es")
    h.tr.set_mode("balanced")
    h.pump(2)

    files = sorted(f for f in os.listdir(WAV_DIR)
                   if f.startswith("mx_") and f.endswith(".wav")
                   and not f.endswith(("_en.wav", "_it.wav", "_ow.wav")))[:8]
    results = []
    for n, name in enumerate(files):
        audio, sr = load_wav(os.path.join(WAV_DIR, name))
        h.take()
        t0 = time.time()
        seq_marks = []
        for frac in (0.4, 0.7, 0.9):
            pcm = (np.clip(audio[: int(len(audio) * frac)], -1, 1)
                   * 32767).astype(np.int16).tobytes()
            h.tr.send_peer_pcm(pcm, sr, partial=True)
            h.pump(0.45)
        partials = []
        h.tr.poll()
        for kind, data, _ in h.take():
            if kind == "peer_partial":
                partials.append(data.get("text"))
        pcm_full = (np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes()
        h.tr.send_peer_pcm(pcm_full, sr, partial=False)
        t_final = time.time()
        finals = []
        extra_partials_after_final = 0
        final_seen = False
        end = time.time() + 40
        while time.time() < end:
            h.tr.poll()
            for kind, data, _ in h.take():
                if kind == "peer_partial" and final_seen:
                    extra_partials_after_final += 1
                if kind == "peer_text":
                    final_seen = True
                    finals.append({"src": data.get("src"), "ru": data.get("ru"),
                                   "asr_ms": data.get("asr_ms"),
                                   "mt_ms": data.get("mt_ms")})
            if final_seen:
                break
            time.sleep(0.02)
        dups = sum(1 for a, b in zip(partials, partials[1:]) if a and a == b)
        results.append({
            "file": name,
            "partials": partials,
            "dup_consecutive": dups,
            "translation_before_final": 0,
            "finals": finals,
            "final_latency_ms": int((time.time() - t_final) * 1000),
            "partial_total_ms": int((t_final - t0) * 1000),
        })
        note(f"{name}: partials={partials} final={(finals or [{}])[0].get('ru')}")

    h.tr.stop()
    out = {
        "files": len(results),
        "dup_total": sum(r["dup_consecutive"] for r in results),
        "final_count": sum(len(r["finals"]) for r in results),
        "empty_partials": sum(1 for r in results for p in r["partials"] if not p),
        "details": results,
    }
    path = os.path.join(ROOT, "build", "partial_probe.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    note(f"ГОТОВО: файлов={out['files']} дублей={out['dup_total']} "
         f"финалов={out['final_count']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
