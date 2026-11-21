"""Замер обратного перевода ES→RU: испанские фразы -> русский.

Вход — `studio_core.PROMPTS_ES` (18 фраз), эталон — `PROMPTS_RU`: испанские
подсказки и есть перевод этих русских фраз, поэтому обратный перевод
обязан вернуть тот же смысл. Оговорка: эталон — ИСХОДНАЯ русская фраза, а
не независимый перевод испанской, поэтому chrF занижен пересказом и
служебными словами; это нижняя оценка смысловой сохранности.

Путь тот же, что в продукте:

    испанский текст -> XTTS (синтез речи) -> Engine.transcribe_peer (ASR
    + определение языка) -> Engine._run_chain (opus-mt es->ru, заданный beam)

Метрики те же, что в `check_accuracy_ru.py`:
  * WER — что услышал ASR (испанский текст против PROMPTS_ES);
  * chrF — что получилось на русском (против PROMPTS_RU).

Режим сравнения `--mt-beams 1,4` переводит ОДИН И ТОТ ЖЕ текст распознавания
разными beam и печатает chrF и время на фразу для каждого: это ответ на
вопрос «стоит ли платить за beam 4».

Запуск (нужен интерпретатор движка: torch + faster-whisper + XTTS):

    "%LOCALAPPDATA%\\Auraloom\\engine\\Scripts\\python.exe" ^
        tools/check_reverse_quality.py --mt-beams 1,4

    # повторно использовать уже синтезированные wav (без загрузки XTTS):
    ... tools/check_reverse_quality.py --mt-beams 1,4 --reuse-audio
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


def read_wav(path: str) -> tuple[np.ndarray, int]:
    with wave.open(path, "rb") as fh:
        sr = fh.getframerate()
        channels = fh.getnchannels()
        raw = fh.readframes(fh.getnframes())
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    return audio, sr


def pcm_bytes(audio: np.ndarray) -> bytes:
    return (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16).tobytes()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=18)
    ap.add_argument("--beam", type=int, default=1,
                    help="beam ASR (как в рабочем режиме Balanced)")
    ap.add_argument("--mt-beams", default="1,4",
                    help="beam перевода через запятую; сравниваются на одном "
                         "и том же тексте распознавания")
    ap.add_argument("--reuse-audio", action="store_true",
                    help="взять готовые wav из out/reverse_es (XTTS не грузим)")
    args = ap.parse_args()

    import studio_core as sc
    import live_translate as lt
    from faster_whisper import WhisperModel

    beams = sorted({int(b) for b in args.mt_beams.split(",") if b.strip()})
    if not beams:
        beams = [lt.MT_BEAMS_REVERSE]
    prod_beam = lt.MT_BEAMS_REVERSE

    pairs = list(zip(sc.PROMPTS_RU, sc.PROMPTS_ES))[:args.limit]
    os.makedirs(OUT_DIR, exist_ok=True)
    audio_paths = {f"q{i:02d}": os.path.join(OUT_DIR, f"q{i:02d}.wav")
                   for i in range(1, len(pairs) + 1)}
    reuse = args.reuse_audio and all(os.path.isfile(p)
                                     for p in audio_paths.values())
    if not reuse and not os.path.isfile(REFERENCE):
        print(f"нет образца голоса для XTTS: {REFERENCE}")
        return 1

    print(f"фраз: {len(pairs)}; ASR {lt.ASR_MODEL}, es->ru beam={beams}"
          f"{' (wav переиспользуются)' if reuse else ' (синтез XTTS)'}")
    t0 = time.time()

    engine = lt.Engine()
    engine.asr = WhisperModel(lt.ASR_MODEL, device="cuda",
                              compute_type=lt.ASR_COMPUTE)
    engine.asr_model = lt.ASR_MODEL
    engine.beam_size = args.beam
    engine.peer_lang = "es"
    engine.peer_lang_confirmed = "es"
    if not reuse:
        engine._load_tts(REFERENCE)
    chain = engine._mt_reverse("es")
    if not chain:
        print("нет модели перевода es->ru")
        return 1
    # прогрев: первый вызов инициализирует матмулы/потоки и врёт по времени
    try:
        engine._run_chain("hola", chain, beam=max(beams), dst="ru")
    except Exception as exc:  # noqa: BLE001
        print(f"прогрев перевода не удался: {exc}")
    print(f"движок готов за {time.time() - t0:.0f} с")

    rows = []
    for i, (ru_ref, es_text) in enumerate(pairs, start=1):
        key = f"q{i:02d}"
        if reuse:
            audio, _sr = read_wav(audio_paths[key])
        else:
            tone, params = lt._tone_params(es_text)
            audio = engine._synth_full(es_text, params, seed=1234 + i * 7919,
                                       lang="es")
            if audio.size == 0:
                print(f"{key}: XTTS не дал звука — пропускаю")
                continue
            write_wav(audio_paths[key], audio, lt.SR_TTS)
        pcm = pcm_bytes(audio)

        asr_t = time.time()
        text_es, _lang = engine.transcribe_peer(pcm, lt.SR_TTS)
        asr_ms = int((time.time() - asr_t) * 1000)

        ru_norm = _norm_ref(ru_ref)
        es_norm = _norm_ref(es_text)
        per_beam = {}
        for beam in beams:
            mt_t = time.time()
            ru = engine._run_chain(text_es, chain, beam=beam, dst="ru")
            mt_ms = int((time.time() - mt_t) * 1000)
            per_beam[beam] = {"ru": ru, "mt_ms": mt_ms,
                              "chrf_ru": round(chrf(ru_norm, ru), 3)}
        row = {
            "id": key, "dur": round(audio.size / float(lt.SR_TTS), 2),
            "es_ref": es_text, "ru_ref": ru_norm, "asr_es": text_es,
            "wer_es": round(wer(es_norm, text_es), 3),
            "asr_ms": asr_ms, "beams": per_beam,
        }
        rows.append(row)
        parts = ", ".join(f"beam {b}: chrF {per_beam[b]['chrf_ru']:.3f}"
                          f" {per_beam[b]['mt_ms']} мс" for b in beams)
        print(f"{key} ({row['dur']} с): WER {row['wer_es']:.2f} | {parts}")

    if not rows:
        print("нет пригодных фраз")
        return 1

    n = len(rows)
    summary = {}
    for beam in beams:
        summary[beam] = {
            "chrf_ru": round(sum(r["beams"][beam]["chrf_ru"]
                                for r in rows) / n, 3),
            "mt_ms": round(sum(r["beams"][beam]["mt_ms"] for r in rows) / n),
            "mt_total_ms": sum(r["beams"][beam]["mt_ms"] for r in rows),
        }
    summary_common = {
        "phrases": n,
        "wer_es": round(sum(r["wer_es"] for r in rows) / n, 3),
        "asr_ms": round(sum(r["asr_ms"] for r in rows) / n),
        "production_beam": prod_beam,
        "tts": "XTTS-v2 (es), reference.wav пользователя",
        "reference_note": ("эталон RU — исходная русская подсказка, "
                           "chrF занижен пересказом"),
    }

    print(f"\nфраз: {n}")
    print(f"  WER ASR (es): {summary_common['wer_es']:.3f}"
          f"   ASR {summary_common['asr_ms']} мс")
    for beam in beams:
        item = summary[beam]
        mark = "  <- в продукте" if beam == prod_beam else ""
        print(f"  beam {beam}: chrF {item['chrf_ru']:.3f}, "
              f"перевод {item['mt_ms']} мс/фразу{mark}")
    if len(beams) > 1:
        base = summary[min(beams)]
        for beam in beams:
            if beam == min(beams):
                continue
            delta_ch = summary[beam]["chrf_ru"] - base["chrf_ru"]
            delta_ms = summary[beam]["mt_ms"] - base["mt_ms"]
            print(f"  beam {beam} против {min(beams)}: chrF "
                  f"{delta_ch:+.3f}, время {delta_ms:+d} мс/фразу")

    out = os.path.join(ROOT, "out", "reverse_quality.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"summary": summary_common, "by_beam": summary,
                   "rows": rows}, fh, ensure_ascii=False, indent=1)
    print(f"json: {out}")
    print(f"звук: {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
