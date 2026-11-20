"""Замер точности живого перевода RU→ES на собственных записях подсказок.

Идея: у каждой записи из `workspace/voice_samples` есть известный текст
(`studio_core.PROMPTS_RU`) и его эталонный перевод (`PROMPTS_ES`). Значит
точность можно мерить числом, а не на слух:

  * WER — доля неверно услышанных слов (распознавание);
  * chrF — совпадение перевода с эталоном по символьным n-граммам (перевод).

Замер идёт ТЕМ ЖЕ кодом, что в продукте: `live_translate.Engine.transcribe`
и `Engine.translate_text`. Предобработка — настоящие `LiveEngine._denoise`
и `_trim_silence` (поэтому подготовка и прогон разделены: движок живёт в
venv с torch, предобработка — в Python приложения с PySide6).

Запуск (два шага, каждый своим интерпретатором):

    python tools/check_accuracy_ru.py --stage prepare
    "%LOCALAPPDATA%\\Auraloom\\engine\\Scripts\\python.exe" ^
        tools/check_accuracy_ru.py --stage run

    # варианты распознавания и перевода
    ... --stage run --beam 1,5 --compute int8_float16,float16 --mt-beams 1,4
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app")
QTAPP = os.path.join(APP, "qtapp")
TOOLS = os.path.join(ROOT, "tools")
SAMPLES = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Auraloom",
                       "workspace", "voice_samples")
PREP = os.path.join(ROOT, "out", "acc")


# --------------------------------------------------------------------------
# метрики
# --------------------------------------------------------------------------
def _tokens(text: str) -> list[str]:
    out, cur = [], []
    for ch in text.lower():
        if ch.isalnum() or ch in "'’-":
            cur.append(ch)
        elif cur:
            out.append("".join(cur))
            cur = []
    if cur:
        out.append("".join(cur))
    return out


def wer(ref: str, hyp: str) -> float:
    """Word error rate (Левенштейн по словам) — 0, если услышано верно."""
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


def _ngrams(text: str, n: int) -> dict:
    s = "".join(_tokens(text))
    s = " " + s + " " if s else ""
    grams = {}
    for i in range(len(s) - n + 1):
        g = s[i:i + n]
        grams[g] = grams.get(g, 0) + 1
    return grams


def chrf(ref: str, hyp: str, max_n: int = 6, beta: float = 2.0) -> float:
    """chrF: F-мера по символьным n-граммам (1…6), без учёта порядка слов."""
    if not ref.strip() and not hyp.strip():
        return 1.0
    if not ref.strip() or not hyp.strip():
        return 0.0
    prec_sum = rec_sum = 0.0
    for n in range(1, max_n + 1):
        rg, hg = _ngrams(ref, n), _ngrams(hyp, n)
        total = sum(hg.values())
        if not total or not sum(rg.values()):
            continue
        hit = sum(min(c, rg.get(g, 0)) for g, c in hg.items())
        prec_sum += hit / total
        rec_sum += hit / sum(rg.values())
    prec = prec_sum / max_n
    rec = rec_sum / max_n
    if prec + rec <= 0:
        return 0.0
    b2 = beta * beta
    return (1 + b2) * prec * rec / (b2 * prec + rec)


# --------------------------------------------------------------------------
# данные
# --------------------------------------------------------------------------
def _prompts() -> tuple[list[str], list[str]]:
    sys.path.insert(0, APP)
    import studio_core  # noqa: PLC0415 — нужен только здесь
    return studio_core.PROMPTS_RU, studio_core.PROMPTS_ES


def _recordings() -> dict[str, str]:
    """p01 → путь первой записи этой подсказки."""
    out: dict[str, str] = {}
    for path in sorted(glob.glob(os.path.join(SAMPLES, "p*_take_*.wav"))):
        key = os.path.basename(path)[:3]
        out.setdefault(key, path)
    return out


def _norm_ref(text: str) -> str:
    """Убрать из эталона то, чего нельзя требовать от распознавания.

    В подсказке 1 стоит `{name}` — имя каждый называет своё, поэтому
    сравнение начинается после «зовут».
    """
    if "{name}" in text:
        head, _, tail = text.partition("{name}")
        return (head.split(" зовут")[0] + " " + tail).strip()
    return text


# --------------------------------------------------------------------------
# шаг prepare: предобработка тем же кодом, что в интерфейсе
# --------------------------------------------------------------------------
def stage_prepare(limit: int) -> int:
    import numpy as np  # noqa: PLC0415

    for p in (APP, QTAPP):
        if p not in sys.path:
            sys.path.insert(0, p)
    from live_engine import LiveEngine  # noqa: PLC0415

    try:
        import soundfile as sf  # noqa: PLC0415
    except ImportError:
        sf = None

    os.makedirs(PREP, exist_ok=True)
    recs = _recordings()
    keys = sorted(recs)[:limit]
    if not keys:
        print(f"нет записей в {SAMPLES}")
        return 1
    for key in keys:
        path = recs[key]
        if sf is not None:
            audio, sr = sf.read(path, dtype="float32")
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
        else:
            with wave.open(path, "rb") as fh:
                sr = fh.getframerate()
                raw = fh.readframes(fh.getnframes())
            audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        audio = np.asarray(audio, dtype=np.float32)
        if sr != 44100:
            print(f"{key}: {sr} Гц — пересэмплировать нечем, пропускаю")
            continue
        # ровно как в _flush_segment перед отправкой в движок
        live = LiveEngine._trim_silence(LiveEngine._denoise(audio))
        for name, signal in (("live", live), ("raw", audio)):
            data = (np.clip(signal, -1.0, 1.0) * 32767).astype(np.int16)
            with wave.open(os.path.join(PREP, f"{key}_{name}.wav"), "wb") as fh:
                fh.setnchannels(1)
                fh.setsampwidth(2)
                fh.setframerate(44100)
                fh.writeframes(data.tobytes())
        print(f"{key}: {os.path.basename(path)} — {len(audio) / 44100:.2f} с")
    print(f"\nготово: {PREP}")
    return 0


# --------------------------------------------------------------------------
# шаг run: распознавание и перевод движком
# --------------------------------------------------------------------------
def stage_run(beams: list[int], computes: list[str], mt_beams: list[int],
              limit: int) -> int:
    import numpy as np  # noqa: PLC0415

    for p in (APP, TOOLS):
        if p not in sys.path:
            sys.path.insert(0, p)
    import live_translate as lt  # noqa: PLC0415
    from faster_whisper import WhisperModel  # noqa: PLC0415

    prompts_ru, prompts_es = _prompts()
    keys = sorted(_recordings())[:limit]
    missing = [k for k in keys
               if not os.path.exists(os.path.join(PREP, f"{k}_live.wav"))]
    if missing:
        print(f"нет подготовленных файлов: {missing[:3]}… "
              f"(сначала --stage prepare)")
        return 1

    def read(name: str) -> tuple[bytes, int]:
        with wave.open(os.path.join(PREP, name), "rb") as fh:
            return fh.readframes(fh.getnframes()), fh.getframerate()

    results: list[dict] = []
    for compute in computes:
        model = WhisperModel(lt.ASR_MODEL, device="cuda", compute_type=compute)
        engine = lt.Engine()
        engine.asr = model
        engine.asr_model = lt.ASR_MODEL
        engine.asr_compute = compute
        engine._asr_loaded_with = compute
        for beam in beams:
            engine.beam_size = beam
            for variant in ("live", "raw"):
                rows = []
                for key in keys:
                    idx = int(key[1:]) - 1
                    pcm, sr = read(f"{key}_{variant}.wav")
                    ru = engine.transcribe(pcm, sr, 0.0)
                    ref_ru = _norm_ref(prompts_ru[idx])
                    rows.append({
                        "id": key,
                        "ru": ru,
                        "ref_ru": ref_ru,
                        "wer": wer(ref_ru, ru),
                    })
                results.append({
                    "name": f"{variant} beam{beam} {compute}",
                    "compute": compute, "beam": beam, "variant": variant,
                    "asr": rows,
                })
        del engine, model
        import torch  # noqa: PLC0415
        torch.cuda.empty_cache()

    # перевод: одна и та же ASR-выдача, разные beam у MT
    mt_engine = lt.Engine()
    best = max(results, key=lambda r: (r["beam"], r["variant"] == "live"))
    for mt_beam in mt_beams:
        lt.MT_BEAMS_FORWARD = mt_beam  # noqa: SLF001 — модульная константа
        # кэш текста иначе вернёт перевод, сделанный предыдущим beam
        mt_engine._ensure_state()  # noqa: SLF001
        mt_engine._text_cache.clear()  # noqa: SLF001
        for row in best["asr"]:
            row.setdefault("mt", {})[str(mt_beam)] = mt_engine.translate_text(
                row["ru"])

    print(f"\n{'вариант':30} {'WER':>7}")
    print("-" * 40)
    summary = []
    for res in results:
        mean_wer = sum(r["wer"] for r in res["asr"]) / len(res["asr"])
        summary.append({"name": res["name"], "wer": round(mean_wer, 3)})
        print(f"{res['name']:30} {mean_wer:7.3f}")

    print(f"\nперевод по выдаче «{best['name']}» ({len(best['asr'])} фраз):")
    mt_scores = {}
    for mt_beam in mt_beams:
        scores = []
        for row in best["asr"]:
            idx = int(row["id"][1:]) - 1
            scores.append(chrf(prompts_es[idx], row["mt"][str(mt_beam)]))
        mt_scores[mt_beam] = round(sum(scores) / len(scores), 3)
        print(f"  MT beam {mt_beam}: chrF {mt_scores[mt_beam]:.3f}")

    print(f"\nхудшие фразы ({best['name']}):")
    for row in sorted(best["asr"], key=lambda r: -r["wer"])[:5]:
        idx = int(row["id"][1:]) - 1
        es = row["mt"][str(mt_beams[0])]
        print(f"  {row['id']} WER={row['wer']:.2f}")
        print(f"    эталон RU: {row['ref_ru']}")
        print(f"    услышано:  {row['ru']}")
        print(f"    эталон ES: {prompts_es[idx]}")
        print(f"    перевод:   {es}")

    out_json = os.path.join(ROOT, "out", "accuracy_ru.json")
    with open(out_json, "w", encoding="utf-8") as fh:
        json.dump({"summary": summary, "mt_chrf": mt_scores,
                   "best": best["name"], "details": results}, fh,
                  ensure_ascii=False, indent=1)
    print(f"\njson: {out_json}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=("prepare", "run"), required=True)
    ap.add_argument("--beam", default="1,5",
                    help="beam распознавания (в продукте — 1)")
    ap.add_argument("--compute", default="int8_float16,float16")
    ap.add_argument("--mt-beams", default="1,4")
    ap.add_argument("--limit", type=int, default=18)
    args = ap.parse_args()
    if args.stage == "prepare":
        return stage_prepare(args.limit)
    return stage_run([int(b) for b in args.beam.split(",")],
                     args.compute.split(","),
                     [int(b) for b in args.mt_beams.split(",")],
                     args.limit)


if __name__ == "__main__":
    raise SystemExit(main())
