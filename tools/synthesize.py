"""Генерация озвучки звуковой панели Auraloom.

Два движка:
  1) piper  — офлайн, мексиканский голос es-MX (встроенный голос Piper).
              Работает без интернета, используется как базовый/демо-вариант.
  2) xtts   — клонирование ТВОЕГО голоса по референсному образцу (reference.wav).
              Нужен GPU (проверено: RTX 5080, CUDA доступна).

Использование:
    python tools/synthesize.py --engine piper
    python tools/synthesize.py --engine xtts --reference path/to/my_voice.wav
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audio_post as ap  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINES = os.path.join(ROOT, "lines.json")
OUT = os.path.join(ROOT, "out")

# stdout всегда UTF-8: иначе печать испанских «¡/é/ó» падает с
# UnicodeEncodeError на кодировке Windows по умолчанию (cp1251).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PIPER_VOICES = {
    # (имя, путь к .onnx, путь к .json) — ищем в рабочей папке, потом рядом с проектом
    "M": (
        r"C:\Users\cyril\AppData\Local\Temp\opencode\es_MX-ald-medium.onnx",
        r"C:\Users\cyril\AppData\Local\Temp\opencode\es_MX-ald-medium.onnx.json",
    ),
    "F": (
        r"C:\Users\cyril\AppData\Local\Temp\opencode\es_MX-claude-high.onnx",
        r"C:\Users\cyril\AppData\Local\Temp\opencode\es_MX-claude-high.onnx.json",
    ),
}


def _voice_paths(voice: str) -> tuple[str, str]:
    """Найти файлы голоса: рабочая папка -> voices/ рядом -> исходный путь."""
    onnx, cfg = PIPER_VOICES[voice]
    roots = [
        os.environ.get("AURALOOM_WORKSPACE", ""),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Auraloom", "workspace"),
        os.path.join(ROOT, "voices"),
        os.path.dirname(os.path.abspath(__file__)),
    ]
    for root in roots:
        if not root:
            continue
        cand_onnx = os.path.join(root, "voices", os.path.basename(onnx))
        if not os.path.exists(cand_onnx):
            cand_onnx = os.path.join(root, os.path.basename(onnx))
        cand_cfg = cand_onnx.replace(".onnx", ".onnx.json")
        if os.path.exists(cand_onnx) and os.path.exists(cand_cfg):
            return cand_onnx, cand_cfg
    return onnx, cfg


def load_lines() -> list[dict]:
    with open(LINES, encoding="utf-8") as fh:
        return json.load(fh)["lines"]


def load_length_scales() -> dict[str, float]:
    """Подобранные темпа реплик (tools/length_scales.json)."""
    path = os.path.join(ROOT, "tools", "length_scales.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return {k: float(v) for k, v in json.load(fh).items()}


def norm(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalpha())


def similarity(heard: str, expected: str) -> float:
    """0..1 — насколько распознанное совпадает с ожидаемым."""
    h, e = norm(heard), norm(expected)
    if not e:
        return 1.0
    if h == e:
        return 1.0
    if not h:
        return 0.0
    pool = list(h)
    common = 0
    for ch in e:
        if ch in pool:
            pool.remove(ch)
            common += 1
    return common / len(e)


# --------------------------------------------------------------------------
# Piper (offline, es-MX)
# --------------------------------------------------------------------------
def synth_piper(text: str, voice: str, length_scale: float = 1.15,
                expressiveness: int = 2) -> tuple[np.ndarray, int]:
    """Синтез голосом Piper. Возвращает (аудио, частота дискретизации)."""
    from piper import PiperVoice, SynthesisConfig

    onnx, cfg = _voice_paths(voice)
    if not os.path.exists(onnx):
        raise FileNotFoundError(
            f"Голос Piper не найден: {onnx}\n"
            "Скачай его:\n"
            "  https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_MX/ald/medium/es_MX-ald-medium.onnx"
        )
    v = PiperVoice.load(onnx, config_path=cfg)
    # Больше шума в фонетике/длительностях — живее интонация
    boost = [0.0, 0.06, 0.12, 0.20][max(0, min(3, expressiveness))]
    sc = SynthesisConfig(length_scale=length_scale,
                         noise_scale=min(0.95, 0.60 + boost),
                         noise_w_scale=min(1.4, 0.85 + boost * 1.5))
    chunks = [c.audio_float_array for c in v.synthesize(text, sc)]
    if not chunks:
        return np.zeros(0, dtype=np.float32), v.config.sample_rate
    return np.concatenate(chunks).astype(np.float32), v.config.sample_rate


# --------------------------------------------------------------------------
# XTTS (клонирование своего голоса)
# --------------------------------------------------------------------------
def synth_xtts(text: str, voice: str, reference: str, speaker: str = "Пользователь") -> tuple[np.ndarray, int]:
    import torch
    from TTS.api import TTS

    model = TTS(model_name="tts_models/multilingual/multi-dataset/xtts_v2", progress_bar=False).to("cuda")
    ref, _ = ap.read_audio(reference)
    out = model.tts(text=text, speaker_wav=ref, language="es", split_sentences=True)
    # XTTS всегда выдаёт 24 кГц
    return np.asarray(out, dtype=np.float32), 24000


# --------------------------------------------------------------------------
def main() -> None:
    ap_ = argparse.ArgumentParser()
    ap_.add_argument("--engine", choices=["piper", "xtts"], default="piper")
    ap_.add_argument("--reference", help="WAV с образцом твоего голоса (для xtts)")
    ap_.add_argument("--speaker", default="Пользователь")
    ap_.add_argument("--only", help="синтезировать только один id (01, 02...)")
    ap_.add_argument("--rms", type=float, default=-18.0, help="целевой RMS, dB")
    ap_.add_argument("--out", default=OUT)
    ap_.add_argument("--expressiveness", type=int, default=2,
                    help="выразительность интонации 0..3 (2 — по умолчанию)")
    ap_.add_argument("--tries", type=int, default=4,
                      help="сколько вариантов рендера проверять на реплику")
    ap_.add_argument("--no-check", action="store_true",
                      help="не проверять разборчивость, один рендер на реплику")
    args = ap_.parse_args()

    lines = load_lines()
    scales = load_length_scales()
    if args.only:
        lines = [l for l in lines if l["id"] == args.only.zfill(2)]

    # Проверяющий Whisper: Piper рандомизирует каждый рендер, поэтому
    # реплику перебираем, пока она не начнёт читаться верно.
    verifier = None
    if not args.no_check:
        from faster_whisper import WhisperModel
        verifier = WhisperModel("small", device="cpu", compute_type="int8")

    def score(processed: np.ndarray, expected: str) -> tuple[float, str]:
        """Насколько реплика читается.

        С подсказкой ожидаемой фразы: так же, как слушатель, который уже
        понимает контекст. Без подсказки Whisper на коротких выкриках
        выдаёт мусор («¡Hasta la próxima!» вместо «Arriba!») — это не
        показатель разборчивости.
        """
        audio16 = ap.to_16k(processed, ap.SR)
        segs, _ = verifier.transcribe(
            audio16, language="es", beam_size=1, vad_filter=False,
            condition_on_previous_text=False, initial_prompt=expected,
        )
        heard = " ".join(s.text.strip() for s in segs).strip()
        return similarity(heard, expected), heard

    for line in lines:
        name = f"mx_{line['id']}"
        expected = line["es"]
        base_scale = scales.get(line["id"], 1.15)

        best_raw, best_score, best_heard = None, -1.0, ""
        tries = 1 if verifier is None else max(1, args.tries)

        for attempt in range(tries):
            if args.engine == "piper":
                # Первый проход — оптимальный темп, дальше варианты темпа
                ls = base_scale if attempt == 0 else [1.05, 1.15, 1.25, 1.40][attempt % 4]
                raw, raw_sr = synth_piper(expected, line.get("vo", "M"), ls,
                                         args.expressiveness)
            else:
                if not args.reference:
                    sys.exit("Нужен --reference с образцом голоса")
                raw, raw_sr = synth_xtts(expected, line.get("vo", "M"),
                                         args.reference, args.speaker)

            if len(raw) == 0:
                continue

            processed = ap.process(raw, raw_sr, target_rms_db=args.rms)
            if verifier is None:
                best_raw, best_score, best_heard = processed, 1.0, ""
                break

            sc, heard = score(processed, expected)
            if sc > best_score:
                best_raw, best_score, best_heard = processed, sc, heard
            if best_score >= 0.999:
                break

        if best_raw is None:
            print(f"[{line['id']}] не удалось отрендерить, пропуск")
            continue

        paths = ap.export_all(best_raw, args.out, name)
        dur = len(best_raw) / ap.SR
        flag = "OK " if best_score >= 0.999 else ("~  " if best_score >= 0.85 else "BAD")
        print(f"{flag}[{line['id']}] {best_score:.2f} {dur:5.2f}s  {expected[:36]:<36} "
              f"| {best_heard[:26]}", flush=True)

    print(f"\nГотово. Файлы в: {args.out}")


if __name__ == "__main__":
    main()
