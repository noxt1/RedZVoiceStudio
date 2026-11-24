"""Почему тихая речь распознаётся хуже громкой: замер по шагам.

Скрипт отвечает на вопрос числом, а не на слух. Один и тот же набор
русских фраз прогоняется через НАСТОЯЩИЙ путь приложения:

    запись -> блоки 50 мс -> LiveEngine._cont_callback (VAD/сегментация)
           -> _trim_silence -> _denoise -> LiveEngine-очередь
           -> Engine.transcribe (проверка уровня, нормализация, Whisper)

и на каждом шаге снимаются уровни. Варианты одной и той же записи:

  base           — как записано;
  quiet_digital  — тише на 18 дБ, шум НЕ менялся (проверка инвариантности
                   тракта к уровню: SNR тот же);
  quiet_noisy    — тише на 18 дБ + шум комнаты на прежнем уровне
                   (реальная тихая речь: SNR падает на ~18 дБ);
  loud           — громче до пика 0.94 (как «говорить громче»).

Разделение важно: если портится только `quiet_noisy`, виновата физика
(SNR), а не обработка. Если портится и `quiet_digital` — тракт не
инвариантен к уровню, и это дефект кода.

Два шага, каждый своим интерпретатором (как в check_accuracy_ru.py):

    python tools/check_mic_gain.py --stage prepare
    "%LOCALAPPDATA%\\Auraloom\\engine\\Scripts\\python.exe" ^
        tools/check_mic_gain.py --stage run

`prepare` использует PySide6 (настоящий LiveEngine), `run` — torch
(настоящий движок). Результаты: out/micgain/prepared.json и
out/micgain/results.json. Записи голоса остаются локально.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import wave

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app")
QTAPP = os.path.join(APP, "qtapp")
TOOLS = os.path.join(ROOT, "tools")
SAMPLES = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Auraloom",
                       "workspace", "voice_samples")
OUT = os.path.join(ROOT, "out", "micgain")
PREPARED = os.path.join(OUT, "prepared.json")
RESULTS = os.path.join(OUT, "results.json")

QUIET_GAIN = 0.126           # -18 дБ
LOUD_PEAK = 0.94


# --------------------------------------------------------------------------
# общее
# --------------------------------------------------------------------------
def _tokens(text: str) -> list[str]:
    out, cur = [], []
    for ch in text.lower():
        if ch.isalnum() or ch in "'’":
            cur.append(ch)
        elif cur:
            out.append("".join(cur))
            cur = []
    if cur:
        out.append("".join(cur))
    return out


def wer(ref: str, hyp: str) -> float:
    """WER по словам; пустая выдача при непустом эталоне = 1.0."""
    r, h = _tokens(ref), _tokens(hyp)
    if not r:
        return 0.0 if not h else 1.0
    prev = list(range(len(h) + 1))
    for i, rw in enumerate(r, 1):
        cur = [i]
        for j, hw in enumerate(h, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                           prev[j - 1] + (rw != hw)))
        prev = cur
    return prev[-1] / len(r)


def _prompts() -> list[str]:
    sys.path.insert(0, APP)
    import studio_core  # noqa: PLC0415
    return studio_core.PROMPTS_RU


def _norm_ref(text: str) -> str:
    if "{name}" in text:
        head, _, tail = text.partition("{name}")
        return (head.split(" зовут")[0] + " " + tail).strip()
    return text


def _recordings() -> dict[str, str]:
    import glob
    out: dict[str, str] = {}
    for path in sorted(glob.glob(os.path.join(SAMPLES, "p*_take_*.wav"))):
        out.setdefault(os.path.basename(path)[:3], path)
    return out


def _read_wav(path: str) -> tuple[np.ndarray, int]:
    with wave.open(path, "rb") as fh:
        sr = fh.getframerate()
        raw = fh.readframes(fh.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0, sr


def _write_wav(path: str, audio: np.ndarray, sr: int) -> None:
    data = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
    with wave.open(path, "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(sr)
        fh.writeframes(data.tobytes())


# --------------------------------------------------------------------------
# шаг prepare: реальный путь GUI (VAD -> trim -> denoise)
# --------------------------------------------------------------------------
def _variants(audio: np.ndarray, sr: int) -> dict[str, np.ndarray]:
    """Четыре уровня одной записи; шум добавляется на прежнем уровне."""
    sys.path.insert(0, QTAPP)
    import audio_diag  # noqa: PLC0415

    noise = audio_diag.noise_rms(audio, sr)
    rng = np.random.default_rng(12345)
    add_noise = rng.normal(0.0, max(noise, 1e-6), size=len(audio)).astype(np.float32)
    peak = float(np.abs(audio).max()) if audio.size else 0.0
    loud_gain = (LOUD_PEAK / peak) if peak > 1e-4 else 1.0
    return {
        "base": audio.copy(),
        "quiet_digital": (audio * QUIET_GAIN).astype(np.float32),
        "quiet_noisy": (audio * QUIET_GAIN + add_noise).astype(np.float32),
        "loud": (audio * loud_gain).astype(np.float32),
    }


def stage_prepare(limit: int) -> int:
    os.makedirs(OUT, exist_ok=True)
    for p in (APP, QTAPP):
        if p not in sys.path:
            sys.path.insert(0, p)
    from PySide6.QtCore import QCoreApplication  # noqa: PLC0415
    _app = QCoreApplication.instance() or QCoreApplication([])
    import live_engine  # noqa: PLC0415
    import audio_diag  # noqa: PLC0415

    prompts = _prompts()
    recs = _recordings()
    keys = sorted(recs)[:limit]
    if not keys:
        print(f"нет записей в {SAMPLES}")
        return 1

    block_sec = live_engine.BLOCK_SEC
    # Настоящий _denoise снимаем ОДИН раз: иначе после прохода «raw»
    # восстанавливался бы уже подменённый метод.
    true_denoise = live_engine.LiveEngine._denoise
    true_trim = live_engine.LiveEngine._trim_silence
    # gui  — как в продукте: обрезка тишины + шумоподавление;
    # raw  — без шумоподавления (влияние trim);
    # pure — без обоих (что вообще снял микрофон).
    kinds = (("gui", True, True), ("raw", False, True), ("pure", False, False))
    rows: list[dict] = []
    for key in keys:
        audio, sr = _read_wav(recs[key])
        if sr != live_engine.SR_REC:
            print(f"{key}: {sr} Гц — ожидается {live_engine.SR_REC}, пропускаю")
            continue
        ref = _norm_ref(prompts[int(key[1:]) - 1])
        for variant, signal in _variants(audio, sr).items():
            # Подаём в НАСТОЯЩИЙ движок сегментации, как поток с микрофона.
            for kind, denoise, trim in kinds:
                engine = live_engine.LiveEngine()
                if not denoise:
                    live_engine.LiveEngine._denoise = staticmethod(lambda x: x)
                if not trim:
                    live_engine.LiveEngine._trim_silence = staticmethod(lambda x: x)
                captured: list[np.ndarray] = []
                engine._queue_translate = (
                    lambda pcm, sr_, out=captured: out.append(pcm))
                engine._cont_on = True
                block = int(sr * block_sec)
                for i in range(0, len(signal) - block + 1, block):
                    chunk = signal[i:i + block].reshape(-1, 1)
                    engine._cont_callback(chunk, block, None, None)
                engine._flush_segment()
                live_engine.LiveEngine._denoise = staticmethod(true_denoise)
                live_engine.LiveEngine._trim_silence = staticmethod(true_trim)
                noise = float(engine._noise)
                seg_rows = []
                for idx, seg in enumerate(captured):
                    name = f"{key}_{variant}_{kind}_{idx}.wav"
                    _write_wav(os.path.join(OUT, name), seg, sr)
                    seg_rows.append({
                        "file": name,
                        "metrics": audio_diag.segment_metrics(seg, sr),
                    })
                rows.append({
                    "id": key, "variant": variant, "kind": kind,
                    "ref": ref, "noise": round(noise, 6),
                    "segments": seg_rows,
                    "produced_audio": bool(captured),
                })
                print(f"{key} {variant:14} {kind}: сегментов {len(captured)}")
            sys.stdout.flush()

    with open(PREPARED, "w", encoding="utf-8") as fh:
        json.dump({"rows": rows}, fh, ensure_ascii=False, indent=1)
    print(f"\nготово: {PREPARED}")
    return 0


# --------------------------------------------------------------------------
# шаг run: реальный движок (проверка уровня + нормализация + Whisper)
# --------------------------------------------------------------------------
def stage_run(limit: int) -> int:
    for p in (APP, TOOLS):
        if p not in sys.path:
            sys.path.insert(0, p)
    import live_translate as lt  # noqa: PLC0415
    from faster_whisper import WhisperModel  # noqa: PLC0415

    with open(PREPARED, "r", encoding="utf-8") as fh:
        prepared = json.load(fh)["rows"]

    model = WhisperModel(lt.ASR_MODEL, device="cuda", compute_type="int8_float16")
    engine = lt.Engine()
    engine.asr = model
    engine.asr_model = lt.ASR_MODEL
    engine.src_lang = "ru"
    engine.beam_size = 1

    agg: dict[tuple, list] = {}
    details: list[dict] = []
    for row in prepared:
        key = (row["variant"], row["kind"])
        if not row["segments"]:
            agg.setdefault(key, []).append(1.0)
            details.append({**{k: row[k] for k in ("id", "variant", "kind",
                                                  "ref")},
                            "ru": "", "wer": 1.0, "reason": "сегмент отброшен"})
            continue
        # Несколько сегментов одной фразы склеиваем: так же, как их слышит
        # пользователь — фраза может прийти двумя репликами.
        parts = []
        for seg in row["segments"]:
            pcm, sr = _read_wav(os.path.join(OUT, seg["file"]))
            parts.append(pcm)
        merged = np.concatenate(parts) if parts else np.zeros(0, np.float32)
        pcm = (np.clip(merged, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
        ru = engine.transcribe(pcm, 44100, float(row["noise"]))
        score = wer(row["ref"], ru)
        agg.setdefault(key, []).append(score)
        details.append({**{k: row[k] for k in ("id", "variant", "kind", "noise")},
                        "ru": ru, "ref": row["ref"], "wer": round(score, 3),
                        "metrics": row["segments"][0]["metrics"]})

    del engine, model
    import torch  # noqa: PLC0415
    torch.cuda.empty_cache()

    print(f"\n{'вариант':16} {'аудио':5} {'WER':>6} {'фраз':>5}")
    print("-" * 38)
    summary = []
    for (variant, kind), scores in sorted(agg.items()):
        mean = sum(scores) / len(scores)
        summary.append({"variant": variant, "kind": kind,
                        "wer": round(mean, 3), "phrases": len(scores)})
        print(f"{variant:16} {kind:5} {mean:6.3f} {len(scores):5}")

    print("\nуровни (средние по фразам, вариант base/gui):")
    for d in details:
        if d["variant"] == "base" and d["kind"] == "gui" and "metrics" in d:
            m = d["metrics"]
            print(f"  {d['id']}: RMS {m['rms_db']} дБ, пик {m['peak_db']} дБ, "
                  f"шум {m['noise_db']} дБ, SNR≈{m['snr_db']} дБ, "
                  f"клип {m['clipping']}, сегмент {m['duration']} с")

    print("\nхудшие фразы (quiet_noisy/gui):")
    worst = [d for d in details if d["variant"] == "quiet_noisy"
             and d["kind"] == "gui"]
    for d in sorted(worst, key=lambda r: -r["wer"])[:5]:
        print(f"  {d['id']} WER={d['wer']:.2f}")
        print(f"    эталон:  {d['ref']}")
        print(f"    услышано:{d['ru'] or ' (пусто)'}")

    with open(RESULTS, "w", encoding="utf-8") as fh:
        json.dump({"summary": summary, "details": details}, fh,
                  ensure_ascii=False, indent=1)
    print(f"\njson: {RESULTS}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=("prepare", "run"), required=True)
    ap.add_argument("--limit", type=int, default=18)
    args = ap.parse_args()
    return stage_prepare(args.limit) if args.stage == "prepare" \
        else stage_run(args.limit)


if __name__ == "__main__":
    raise SystemExit(main())
