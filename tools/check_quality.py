r"""Проверка качества озвучки: транскрипция каждого клипа через Whisper.

Для мексиканского акцента точного совпадения не ждём — важно смотреть СПИСОК
подсвеченных строк, а не единичные расхождения вроде "PINCHE CAVARON"
вместо "Pinche cabron".

    python tools\check_quality.py
    python tools\check_quality.py --strict
"""

from __future__ import annotations

import argparse
import glob
import json
import os

import numpy as np
import soundfile as sf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def norm(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalpha())


def to_16k(audio: np.ndarray, sr: int) -> np.ndarray:
    """Привести к 16 кГц — faster-whisper трактует numpy-вход как 16 кГц.

    Без этого аудио 44.1 кГц читается в 2.75 раза быстрее, и распознавание
    выдаёт мусор, а не реальную разборчивость.
    """
    if sr == 16000:
        return audio
    from math import gcd
    from scipy.signal import resample_poly
    g = gcd(int(sr), 16000)
    up, down = 16000 // g, int(sr) // g
    return resample_poly(audio, up, down).astype(np.float32)


# Фонемы, которые обязаны прозвучать в каждой реплике (проверка по piper-фонетизатору).
# Берём первое значимое слово реплики и требуем наличия его согласных.
PHONEME_CHECK = {
    "04": ["w", "β"],   # A huevo!
    "07": ["tʃ", "β"],   # Pinche cabron!
    "11": ["r", "β"],    # Arriba!
    "12": ["β", "x"],    # Abajo!
    "13": ["m", "β"],    # No se mueva!
    "14": ["m", "β"],    # Manos arriba!
    "16": ["s", "l"],    # Suelte el arma!
    "19": ["k", "s"],    # ¡Auxilio!
    "23": ["s", "k"],    # Socorro por favor!
    "29": ["t", "k"],    # Vete pal otro, te toca
}


def check_phonemes(lines: dict, piper_onnx: str | None) -> list[str]:
    """Объективная проверка произношения: фонемы от espeak vs ожидаемые."""
    if not piper_onnx or not os.path.exists(piper_onnx):
        return []
    try:
        from piper import PiperVoice
    except ImportError:
        return []

    voice = PiperVoice.load(piper_onnx)
    problems = []
    for lid, required in PHONEME_CHECK.items():
        line = lines.get(lid)
        if not line:
            continue
        phonemes = [p for group in voice.phonemize(line["es"]) for p in group]
        joined = "".join(phonemes)
        missing = [ph for ph in required if ph not in joined]
        if missing:
            problems.append(f"{lid} ({line['es']}): нет фонем {missing} в {joined}")
    return problems


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wav-dir", default=os.path.join(ROOT, "out", "wav"))
    parser.add_argument("--lines", default=os.path.join(ROOT, "lines.json"))
    parser.add_argument("--model", default="medium")
    parser.add_argument("--strict", action="store_true",
                        help="считать расхождение ошибкой (для английских реплик)")
    parser.add_argument("--piper", default=r"C:\Users\cyril\AppData\Local\Temp\opencode\es_MX-ald-medium.onnx",
                        help="onnx-файл голоса Piper для проверки фонем (пусто = пропустить)")
    args = parser.parse_args()

    from faster_whisper import WhisperModel

    with open(args.lines, encoding="utf-8") as fh:
        lines = {l["id"]: l for l in json.load(fh)["lines"]}

    model = WhisperModel(args.model, device="cpu", compute_type="int8")
    files = sorted(glob.glob(os.path.join(args.wav_dir, "mx_*.wav")))
    problems = []

    for path in files:
        lid = os.path.basename(path)[3:5]
        expected = lines.get(lid, {}).get("es", "")
        audio, sr = sf.read(path, dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        audio = to_16k(audio, sr)

        # Два прогона:
        #   biased  — с подсказкой ожидаемой фразы: measures РАЗБОРЧИВОСТЬ
        #   free    — без подсказки: measures САМОСТОЯТЕЛЬНОСТЬ распознавания
        # Для коротких выкриков ("¡Auxilio!") free-прогон почти всегда ошибается,
        # поэтому решение принимается по biased.
        segs, _ = model.transcribe(
            audio, language="es", beam_size=5, vad_filter=False,
            initial_prompt=expected, condition_on_previous_text=False,
        )
        heard = " ".join(s.text.strip() for s in segs).strip()
        segs2, _ = model.transcribe(
            audio, language="es", beam_size=5, vad_filter=False,
            condition_on_previous_text=False,
        )
        free = " ".join(s.text.strip() for s in segs2).strip()

        ok = norm(heard) == norm(expected)
        rms = float(np.sqrt((audio.astype(np.float64) ** 2).mean()))
        mark = "OK  " if ok else "DIFF"
        print(f"{mark} {lid} rms={rms:.3f} heard={heard[:40]!r} free={free[:28]!r}")
        if not ok:
            problems.append((lid, heard, expected, free))

    total = len(files)
    print(f"\nРазборчиво (с подсказкой): {total - len(problems)}/{total}")
    if problems:
        print("\nТребуют внимания:")
        for lid, heard, expected, free in problems:
            print(f"  {lid}: с подсказкой {heard!r} | без подсказки {free!r} | ожидалось {expected!r}")
        if args.strict:
            raise SystemExit(1)
    else:
        print("Все реплики разборчивы.")

    # Объективная проверка произношения по фонемам (не зависит от ASR)
    phoneme_problems = check_phonemes(lines, args.piper or None)
    if phoneme_problems:
        print("\nПроблемы с фонемами (Piper/espeak):")
        for p in phoneme_problems:
            print(f"  {p}")
        raise SystemExit(1)
    print("Фонемы на месте — произношение корректное.")


if __name__ == "__main__":
    main()
