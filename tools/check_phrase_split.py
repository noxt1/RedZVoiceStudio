"""Замер: сколько смысла теряется, когда фраза переводится кусками.

Жалоба: собеседник говорит быстро — приложение переводит первую часть,
потом вторую, и смысл получается другой. Здесь это измеряется на
реальных записях подсказок (workspace/voice_samples):

  * «куски» — запись режется по самой тихой внутренней паузе, каждая
    половина распознаётся и переводится ОТДЕЛЬНО (так работал движок,
    когда длинная реплика собеседника уходила кусками по 5 с);
  * «целиком» — та же запись распознаётся и переводится одним куском
   (так работает после склейки кусков).

Метрики те же, что в tools/check_accuracy_ru.py: WER по распознаванию и
chrF перевода против эталона studio_core.PROMPTS_ES.

Направление замера — RU→ES: для него есть и записи, и эталонный перевод.
Механизм потери контекста от направления не зависит (ASR видит огрызок,
MT переводит огрызок), поэтому вывод переносится и на ES→RU.

Запуск (нужен интерпретатор движка: torch + faster-whisper):

    "%LOCALAPPDATA%\\Auraloom\\engine\\Scripts\\python.exe" ^
        tools/check_phrase_split.py
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import wave

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app")
TOOLS = os.path.join(ROOT, "tools")
SAMPLES = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Auraloom",
                       "workspace", "voice_samples")

sys.path.insert(0, TOOLS)
from check_accuracy_ru import _norm_ref, _prompts, chrf, wer  # noqa: E402


def read_wav(path: str) -> tuple[np.ndarray, int]:
    with wave.open(path, "rb") as fh:
        sr = fh.getframerate()
        channels = fh.getnchannels()
        raw = fh.readframes(fh.getnframes())
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    return audio, sr


def quietest_split(audio: np.ndarray, sr: int,
                   window: float = 0.30) -> int | None:
    """Центр самой тихой паузы в середине записи (индекс сэмпла)."""
    win = int(window * sr)
    step = max(1, int(0.05 * sr))
    lo = int(len(audio) * 0.15)
    hi = int(len(audio) * 0.85) - win
    if hi <= lo:
        return None
    best_pos, best_rms = None, None
    for pos in range(lo, hi, step):
        piece = audio[pos:pos + win].astype(np.float64)
        rms = float(np.sqrt(np.mean(piece ** 2)))
        if best_rms is None or rms < best_rms:
            best_pos, best_rms = pos, rms
    if best_pos is None:
        return None
    return best_pos + win // 2


def pcm_bytes(audio: np.ndarray) -> bytes:
    return (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16).tobytes()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=18)
    ap.add_argument("--beam", type=int, default=1)
    args = ap.parse_args()

    import live_translate as lt
    from faster_whisper import WhisperModel

    prompts_ru, prompts_es = _prompts()
    recs: dict[str, str] = {}
    for path in sorted(glob.glob(os.path.join(SAMPLES, "p*_take_*.wav"))):
        recs.setdefault(os.path.basename(path)[:3], path)
    keys = sorted(recs)[:args.limit]
    if not keys:
        print(f"нет записей в {SAMPLES}")
        return 1

    model = WhisperModel(lt.ASR_MODEL, device="cuda",
                         compute_type=lt.ASR_COMPUTE)
    engine = lt.Engine()
    engine.asr = model
    engine.asr_model = lt.ASR_MODEL
    engine.beam_size = args.beam
    engine.src_lang = "ru"
    engine.lang = "es"

    rows = []
    for key in keys:
        idx = int(key[1:]) - 1
        audio, sr = read_wav(recs[key])
        cut = quietest_split(audio, sr)
        if cut is None or cut < int(0.5 * sr) \
                or len(audio) - cut < int(0.5 * sr):
            print(f"{key}: нет внутренней паузы — пропускаю")
            continue
        head, tail = audio[:cut], audio[cut:]

        ru_head = engine.transcribe(pcm_bytes(head), sr, 0.0)
        ru_tail = engine.transcribe(pcm_bytes(tail), sr, 0.0)
        ru_split = (ru_head + " " + ru_tail).strip()

        ru_whole = engine.transcribe(pcm_bytes(audio), sr, 0.0)

        es_split = " ".join(
            part for part in (engine.translate_text(ru_head),
                              engine.translate_text(ru_tail)) if part)
        es_whole = engine.translate_text(ru_whole)

        ref_ru = _norm_ref(prompts_ru[idx])
        ref_es = prompts_es[idx]
        rows.append({
            "id": key,
            "split_at": round(cut / sr, 2),
            "dur": round(len(audio) / sr, 2),
            "ru_head": ru_head, "ru_tail": ru_tail, "ru_whole": ru_whole,
            "es_split": es_split, "es_whole": es_whole,
            "wer_split": round(wer(ref_ru, ru_split), 3),
            "wer_whole": round(wer(ref_ru, ru_whole), 3),
            "chrf_split": round(chrf(ref_es, es_split), 3),
            "chrf_whole": round(chrf(ref_es, es_whole), 3),
        })
        print(f"{key} ({rows[-1]['dur']} с, разрез на {rows[-1]['split_at']} с): "
              f"ASR {rows[-1]['wer_split']:.2f} -> {rows[-1]['wer_whole']:.2f}, "
              f"chrF {rows[-1]['chrf_split']:.3f} -> "
              f"{rows[-1]['chrf_whole']:.3f}")

    if not rows:
        print("нет пригодных записей")
        return 1
    n = len(rows)
    summary = {
        "phrases": n,
        "wer_split": round(sum(r["wer_split"] for r in rows) / n, 3),
        "wer_whole": round(sum(r["wer_whole"] for r in rows) / n, 3),
        "chrf_split": round(sum(r["chrf_split"] for r in rows) / n, 3),
        "chrf_whole": round(sum(r["chrf_whole"] for r in rows) / n, 3),
    }
    print(f"\nфраз: {n}")
    print(f"  WER  кусками: {summary['wer_split']:.3f}   целиком: "
          f"{summary['wer_whole']:.3f}")
    print(f"  chrF кусками: {summary['chrf_split']:.3f}   целиком: "
          f"{summary['chrf_whole']:.3f}")
    worse = sum(1 for r in rows if r["chrf_split"] < r["chrf_whole"])
    print(f"  куски хуже цельной фразы: {worse} из {n}")

    out = os.path.join(ROOT, "out", "phrase_split.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"summary": summary, "rows": rows}, fh,
                  ensure_ascii=False, indent=1)
    print(f"json: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
