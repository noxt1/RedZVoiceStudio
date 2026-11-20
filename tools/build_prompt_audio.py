"""Заранее озвучить все подсказки и положить готовые WAV в voices/prompts/.

Зачем: приложение должно проигрывать образец интонации МГНОВЕННО и без
сети. Piper на месте есть, но каждая синтезация занимает секунды (загрузка
модели) — для 18 фраз это полминуты ожидания. Поэтому референсы
озвучиваются один раз на сборочной машине и едут вместе с программой.

Запуск:
    python tools/build_prompt_audio.py [--voice es_MX-claude-high]

Лицензии (см. voices/THIRD-PARTY-NOTICES.md):
    piper            — MIT
    es_MX-ald-medium — Unlicense (public domain)
    es_MX-claude-high— Apache-2.0
    Готовые WAV — производные от голоса es_MX-claude-high (Apache-2.0),
    поэтому распространяются свободно.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

import studio_core as core  # noqa: E402

OUT_DIR = os.path.join(ROOT, "voices", "prompts")
SR = 22050

# Подача под эмоцию: (length_scale, noise_scale, noise_w_scale, volume)
PROSODY = {
    "angry":     {"length_scale": 0.90, "noise_scale": 0.80, "noise_w_scale": 1.20, "volume": 1.00},
    "friendly":  {"length_scale": 1.12, "noise_scale": 0.58, "noise_w_scale": 0.80, "volume": 0.92},
    "neutral":   {"length_scale": 1.00, "noise_scale": 0.667, "noise_w_scale": 0.80, "volume": 0.95},
    "energetic": {"length_scale": 0.94, "noise_scale": 0.75, "noise_w_scale": 1.05, "volume": 1.00},
}

LABELS = {
    "angry": "возмущённо, резко",
    "friendly": "тепло, дружелюбно",
    "energetic": "энергично, живо",
    "neutral": "спокойно, обычно",
}


def find_voice(name: str) -> str:
    for base in (os.path.join(ROOT, "voices"),):
        p = os.path.join(base, name + ".onnx")
        if os.path.exists(p):
            return p
    raise SystemExit(f"голос не найден: {name}.onnx в {os.path.join(ROOT, 'voices')}")


def synthesize(voice, text: str, emotion: str) -> np.ndarray:
    from piper import SynthesisConfig

    style = PROSODY.get(emotion, PROSODY["neutral"])
    cfg = SynthesisConfig(
        length_scale=style["length_scale"],
        noise_scale=style["noise_scale"],
        noise_w_scale=style["noise_w_scale"],
        volume=style["volume"],
        normalize_audio=False,
    )
    chunks = [np.asarray(c.audio_float_array, dtype=np.float32)
              for c in voice.synthesize(text, cfg)]
    if not chunks:
        raise RuntimeError(f"пустая озвучка: {text}")
    audio = np.concatenate(chunks)
    peak = float(np.abs(audio).max()) if audio.size else 0.0
    if peak > 0:
        audio = audio * (0.89 / peak)
    # мягкая пауза на краях, чтобы не было щелчков
    pad = np.zeros(int(SR * 0.04), dtype=np.float32)
    return np.concatenate([pad, audio, pad])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", default="es_MX-claude-high")
    args = ap.parse_args()

    from piper import PiperVoice

    onnx = find_voice(args.voice)
    print(f">>> голос: {onnx}")
    os.makedirs(OUT_DIR, exist_ok=True)

    print(">>> загружаю модель…")
    voice = PiperVoice.load(onnx)

    manifest = []
    for i, (ru, es) in enumerate(zip(core.PROMPTS_RU, core.PROMPTS_ES)):
        emotion = (core.PROMPT_EMOTIONS[i]
                   if i < len(core.PROMPT_EMOTIONS) else "neutral")
        text_es = es.replace("{name}", core.PROMPT_REF_NAME)
        text_ru = ru.replace("{name}", "{name}")

        audio = synthesize(voice, text_es, emotion)
        name = f"prompt_{i + 1:02d}.wav"
        path = os.path.join(OUT_DIR, name)
        sf.write(path, audio, SR, subtype="PCM_16")
        dur = len(audio) / SR
        manifest.append({
            "index": i,
            "file": name,
            "ru": text_ru,
            "es": text_es,
            "emotion": emotion,
            "emotion_label": LABELS.get(emotion, emotion),
            "duration": round(dur, 2),
        })
        print(f"  {i + 1:2d}/{len(core.PROMPTS_RU)}  {emotion:10} "
              f"{dur:5.2f} c  {name}  «{text_es[:44]}»")

    with open(os.path.join(OUT_DIR, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump({
            "voice": args.voice,
            "samplerate": SR,
            "ref_name": core.PROMPT_REF_NAME,
            "license": "Apache-2.0 (es_MX-claude-high) + MIT (piper)",
            "items": manifest,
        }, fh, ensure_ascii=False, indent=1)

    total = sum(m["duration"] for m in manifest)
    size = sum(os.path.getsize(os.path.join(OUT_DIR, m["file"])) for m in manifest)
    print(f">>> готово: {len(manifest)} файлов, {total:.1f} c, {size / 1048576:.2f} МБ")
    print(f">>> {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
