"""Первый замер обратного перевода ES→RU: испанские фразы -> русский.

До сих пор качество обратного направления не измерялось: цифры были только
для RU→ES (свои записи подсказок). Здесь меряется то же самое, но в другую
сторону, НАСТОЯЩИМ кодом движка:

    испанский текст -> XTTS (синтез речи) -> Engine.transcribe_peer (ASR
    + определение языка) -> Engine._translate_peer_to_ru (opus-mt es->ru,
    beam 4)

Вход — `studio_core.PROMPTS_ES` (18 фраз), эталон — `PROMPTS_RU`: испанские
подсказки и есть перевод этих русских фраз, поэтому обратный перевод
обязан вернуть тот же смысл. Оговорка: эталон — ИСХОДНАЯ русская фраза, а
не независимый перевод испанской, поэтому chrF занижен пересказом и
служебными словами; это нижняя оценка смысловой сохранности, а не потолок
качества перевода.

Метрики те же, что в `check_accuracy_ru.py`:
  * WER — что услышал ASR (испанский текст против PROMPTS_ES);
  * chrF — что получилось на русском (против PROMPTS_RU).
Дополнительно: сколько фраз автоопределение языка приняло бы (режим auto)
и сколько осталось без перевода.

Запуск (нужен интерпретатор движка: torch + faster-whisper + XTTS):

    "%LOCALAPPDATA%\\Auraloom\\engine\\Scripts\\python.exe" ^
        tools/check_reverse_quality.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import wave

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app")
TOOLS = os.path.join(ROOT, "tools")
WORKSPACE = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Auraloom",
                         "workspace")
REFERENCE = os.path.join(WORKSPACE, "reference.wav")
OUT_DIR = os.path.join(ROOT, "out", "reverse_es")

sys.path.insert(0, TOOLS)
sys.path.insert(0, APP)
from check_accuracy_ru import _norm_ref, chrf, wer  # noqa: E402


def write_wav(path: str, audio: np.ndarray, sr: int) -> None:
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
    with wave.open(path, "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(sr)
        fh.writeframes(pcm.tobytes())


def pcm_bytes(audio: np.ndarray) -> bytes:
    return (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16).tobytes()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=18)
    ap.add_argument("--beam", type=int, default=1,
                    help="beam ASR (как в рабочем режиме Balanced)")
    args = ap.parse_args()

    import studio_core as sc
    import live_translate as lt
    from faster_whisper import WhisperModel

    if not os.path.isfile(REFERENCE):
        print(f"нет образца голоса для XTTS: {REFERENCE}")
        return 1

    pairs = list(zip(sc.PROMPTS_RU, sc.PROMPTS_ES))[:args.limit]
    os.makedirs(OUT_DIR, exist_ok=True)

    print(f"фраз: {len(pairs)}; синтез XTTS (es), ASR {lt.ASR_MODEL}, "
          f"перевод es->ru beam={lt.MT_BEAMS_REVERSE}")
    t0 = time.time()

    engine = lt.Engine()
    engine.asr = WhisperModel(lt.ASR_MODEL, device="cuda",
                              compute_type=lt.ASR_COMPUTE)
    engine.asr_model = lt.ASR_MODEL
    engine.beam_size = args.beam
    engine.peer_lang = "es"
    engine.peer_lang_confirmed = "es"
    engine._load_tts(REFERENCE)
    print(f"движок готов за {time.time() - t0:.0f} с")

    rows = []
    for i, (ru_ref, es_text) in enumerate(pairs, start=1):
        key = f"q{i:02d}"
        tone, params = lt._tone_params(es_text)
        audio = engine._synth_full(es_text, params, seed=1234 + i * 7919,
                                   lang="es")
        if audio.size == 0:
            print(f"{key}: XTTS не дал звука — пропускаю")
            continue
        path = os.path.join(OUT_DIR, f"{key}.wav")
        write_wav(path, audio, lt.SR_TTS)
        pcm = pcm_bytes(audio)

        # 1) как в режиме auto: примет ли движок язык этой фразы
        engine.peer_lang = "auto"
        engine.peer_lang_confirmed = ""
        engine._lang_hits = []
        text_auto, _lang_auto = engine.transcribe_peer(pcm, lt.SR_TTS)
        auto_ok = bool(text_auto)

        # 2) ручной выбор «испанский» — так измеряется сам перевод
        engine.peer_lang = "es"
        engine.peer_lang_confirmed = "es"
        asr_t = time.time()
        text_es, _lang = engine.transcribe_peer(pcm, lt.SR_TTS)
        asr_ms = int((time.time() - asr_t) * 1000)
        mt_t = time.time()
        ru = engine._translate_peer_to_ru(text_es, "es", pcm, lt.SR_TTS)
        mt_ms = int((time.time() - mt_t) * 1000)

        ru_norm = _norm_ref(ru_ref)
        es_norm = _norm_ref(es_text)
        row = {
            "id": key, "dur": round(audio.size / float(lt.SR_TTS), 2),
            "es_ref": es_text, "ru_ref": ru_norm,
            "asr_es": text_es, "ru": ru,
            "auto_accepted": auto_ok,
            "wer_es": round(wer(es_norm, text_es), 3),
            "chrf_ru": round(chrf(ru_norm, ru), 3),
            "asr_ms": asr_ms, "mt_ms": mt_ms,
        }
        rows.append(row)
        print(f"{key} ({row['dur']} с, auto={'да' if auto_ok else 'нет'}): "
              f"WER {row['wer_es']:.2f}, chrF {row['chrf_ru']:.3f} | "
              f"{text_es!r} -> {ru!r}")

    if not rows:
        print("нет пригодных фраз")
        return 1

    n = len(rows)
    summary = {
        "phrases": n,
        "wer_es": round(sum(r["wer_es"] for r in rows) / n, 3),
        "chrf_ru": round(sum(r["chrf_ru"] for r in rows) / n, 3),
        "auto_accepted": sum(1 for r in rows if r["auto_accepted"]),
        "empty_ru": sum(1 for r in rows if not r["ru"].strip()),
        "asr_ms": round(sum(r["asr_ms"] for r in rows) / n),
        "mt_ms": round(sum(r["mt_ms"] for r in rows) / n),
        "tts": "XTTS-v2 (es), reference.wav пользователя",
        "reference_note": ("эталон RU — исходная русская подсказка, "
                           "chrF занижен пересказом"),
    }
    print(f"\nфраз: {n}")
    print(f"  WER ASR (es): {summary['wer_es']:.3f}")
    print(f"  chrF перевода (ru): {summary['chrf_ru']:.3f}")
    print(f"  автоопределение приняло бы: {summary['auto_accepted']} из {n}")
    print(f"  без перевода: {summary['empty_ru']} из {n}")
    print(f"  ASR {summary['asr_ms']} мс, перевод {summary['mt_ms']} мс")

    out = os.path.join(ROOT, "out", "reverse_quality.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"summary": summary, "rows": rows}, fh,
                  ensure_ascii=False, indent=1)
    print(f"json: {out}")
    print(f"звук: {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
