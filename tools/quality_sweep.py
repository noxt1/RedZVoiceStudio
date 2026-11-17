"""Замер качества: варианты декодирования MT и настройки XTTS.

Запускать интерпретатором движка (нужны torch/transformers/TTS):
    engine\\Scripts\\python.exe build\\quality_sweep.py

1. MT: реальные пары ru/es из lines.json. Считаем chrF (символьный F-мер)
   и время для greedy / beam4 / beam4+штрафы / beam6.
2. TTS: синтез испанских фраз с разными параметрами, обратное распознавание
   тем же Whisper -> WER (разборчивость), плюс время до первого чанка.
"""
from __future__ import annotations

import io
import json
import os
import sys
import time

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("COQUI_TOS_AGREED", "1")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
sys.path.insert(0, TOOLS)

import numpy as np  # noqa: E402

OUT = os.path.join(ROOT, "build", "quality_sweep.json")


# ---------------------------------------------------------------- метрики
def _ngrams(s: str, n: int) -> dict:
    s = " " + " ".join(s.split()) + " "
    out: dict[str, int] = {}
    for i in range(len(s) - n + 1):
        g = s[i:i + n]
        out[g] = out.get(g, 0) + 1
    return out


def chrf(hyp: str, ref: str, max_n: int = 6) -> float:
    scores = []
    for n in range(1, max_n + 1):
        h, r = _ngrams(hyp.lower(), n), _ngrams(ref.lower(), n)
        overlap = sum(min(c, r.get(g, 0)) for g, c in h.items())
        prec = overlap / max(1, sum(h.values()))
        rec = overlap / max(1, sum(r.values()))
        scores.append(0.0 if prec + rec == 0 else 2 * prec * rec / (prec + rec))
    return round(100 * sum(scores) / len(scores), 1)


def wer(hyp: str, ref: str) -> float:
    def norm(t):
        return [w.strip("¿?¡!.,;:«»\"'").lower() for w in t.split() if w.strip()]
    h, r = norm(hyp), norm(ref)
    if not r:
        return 1.0
    d = np.zeros((len(h) + 1, len(r) + 1), dtype=int)
    for i in range(len(h) + 1):
        d[i][0] = i
    for j in range(len(r) + 1):
        d[0][j] = j
    for i in range(1, len(h) + 1):
        for j in range(1, len(r) + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1,
                          d[i - 1][j - 1] + (h[i - 1] != r[j - 1]))
    return round(float(d[len(h)][len(r)]) / len(r), 3)


# ---------------------------------------------------------------- данные
def load_pairs(limit: int = 12) -> list[dict]:
    with io.open(os.path.join(ROOT, "lines.json"), encoding="utf-8") as fh:
        items = json.load(fh)["lines"]
    pairs = []
    for it in items:
        es, ru = (it.get("es") or "").strip(), (it.get("ru") or "").strip()
        if es and ru and len(ru.split()) >= 2:
            pairs.append({"es": es, "ru": ru})
        if len(pairs) >= limit:
            break
    return pairs


# ---------------------------------------------------------------- MT
def mt_sweep(pairs: list[dict]) -> dict:
    import torch
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    configs = [
        ("greedy (сейчас)", {"num_beams": 1}),
        ("beam4", {"num_beams": 4}),
        ("beam4+no_repeat3", {"num_beams": 4, "no_repeat_ngram_size": 3}),
        ("beam5+len1.2", {"num_beams": 5, "length_penalty": 1.2,
                          "no_repeat_ngram_size": 3}),
    ]
    result: dict[str, list] = {"ru->es": [], "es->ru": []}
    for pair in ("ru->es", "es->ru"):
        src, dst = pair.split("->")
        name = f"Helsinki-NLP/opus-mt-{src}-{dst}"
        tok = AutoTokenizer.from_pretrained(name)
        model = AutoModelForSeq2SeqLM.from_pretrained(
            name, dtype=torch.float16, low_cpu_mem_usage=True).eval()
        for label, kw in configs:
            scores, times, samples = [], [], []
            for p in pairs:
                text = p[src]
                batch = tok([text], return_tensors="pt", padding=True,
                            truncation=True)
                t0 = time.time()
                with torch.inference_mode():
                    out = model.generate(**batch, max_new_tokens=128, **kw)
                times.append((time.time() - t0) * 1000)
                hyp = tok.batch_decode(out, skip_special_tokens=True)[0].strip()
                scores.append(chrf(hyp, p[dst]))
                if len(samples) < 3:
                    samples.append({"src": text, "hyp": hyp, "ref": p[dst]})
            result[pair].append({
                "config": label,
                "chrf": round(sum(scores) / len(scores), 1),
                "ms_p50": round(sorted(times)[len(times) // 2], 1),
                "samples": samples,
            })
            print(f"[MT] {pair} {label}: chrF={result[pair][-1]['chrf']} "
                  f"{result[pair][-1]['ms_p50']} мс", flush=True)
        del model, tok
        torch.cuda.empty_cache() if torch.cuda.is_available() else None
    return result


# ---------------------------------------------------------------- TTS
TTS_CONFIGS = [
    ("как сейчас (neutral)", {"temperature": 0.75, "top_p": 0.86, "top_k": 50,
                              "speed": 1.02, "repetition_penalty": 10.0}),
    ("выше потолок 0.85", {"temperature": 0.85, "top_p": 0.92, "top_k": 70,
                           "speed": 0.99, "repetition_penalty": 10.0}),
    ("спокойнее/чётче", {"temperature": 0.65, "top_p": 0.80, "top_k": 40,
                        "speed": 0.97, "repetition_penalty": 10.0}),
    ("быстрее (speed 1.06)", {"temperature": 0.75, "top_p": 0.86, "top_k": 50,
                              "speed": 1.06, "repetition_penalty": 10.0}),
]

TTS_TEXTS = [
    "No manches, guey, ya me tienes harto.",
    "Oye, que bueno verte, hermano.",
    "Pinche cabron, te voy a madrear.",
    "Vamos por unas chelas al centro, va?",
]


def tts_sweep(reference: str) -> list[dict]:
    import live_translate as lt
    from faster_whisper import WhisperModel

    eng = object.__new__(lt.Engine)
    eng.stream_chunk = 30
    eng._load_tts(reference)

    asr = WhisperModel("mobiuslabsgmbh/faster-whisper-large-v3-turbo",
                       device="cuda", compute_type="int8_float16")
    out = []
    for label, params in TTS_CONFIGS:
        wers, firsts, durs = [], [], []
        for text in TTS_TEXTS:
            t0 = time.time()
            first_ms = None
            parts = []
            try:
                for c in eng.tts.inference_stream(
                        text, "es", eng.gpt_latent, eng.spk_emb,
                        stream_chunk_size=eng.stream_chunk,
                        overlap_wav_len=2048, **params):
                    if first_ms is None:
                        first_ms = int((time.time() - t0) * 1000)
                    parts.append(c.detach().cpu().numpy().reshape(-1))
            except Exception as exc:  # noqa: BLE001
                print(f"[TTS] {label}: ошибка синтеза {exc}", flush=True)
                break
            if not parts:
                continue
            audio = np.concatenate(parts).astype(np.float32)
            want = int(24000 * 3)  # первые 3 с достаточно для разборчивости
            cut = audio[:want]
            segs, _info = asr.transcribe(cut, language="es", beam_size=1,
                                         vad_filter=False,
                                         condition_on_previous_text=False)
            heard = " ".join(s.text.strip() for s in segs).strip()
            wers.append(wer(heard, text))
            if first_ms is not None:
                firsts.append(first_ms)
            durs.append(round(len(audio) / 24000.0, 2))
            print(f"[TTS] {label}: {heard!r} WER={wers[-1]}", flush=True)
        if wers:
            out.append({
                "config": label, "params": params,
                "wer": round(float(np.mean(wers)), 3),
                "first_ms": int(np.mean(firsts)) if firsts else None,
                "seconds": round(float(np.mean(durs)), 2),
            })
    return out


def main() -> int:
    pairs = load_pairs()
    print(f"пар: {len(pairs)}", flush=True)
    res = {"pairs": len(pairs), "mt": mt_sweep(pairs)}
    ref = os.path.join(os.environ["LOCALAPPDATA"], "Auraloom", "workspace",
                       "reference.wav")
    if os.path.exists(ref):
        res["tts"] = tts_sweep(ref)
    else:
        res["tts"] = []
        print("нет reference.wav — синтез не мерился", flush=True)
    with io.open(OUT, "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=2)
    print("ГОТОВО", OUT, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
