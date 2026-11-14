"""Замер 3: ЛОКАЛЬНЫЙ перевод RU->ES на GPU (без сети).

Сетевой перевод занимал ~1768 мс — это узкое место. Локальная модель
Helsinki-NLP/opus-mt-ru-es (Apache-2.0, 309 МБ) должна быть в разы быстрее.

Запуск (движок с torch/transformers):
    "<engine>\\Scripts\\python.exe" research\\bench_local_translate.py
"""

from __future__ import annotations

import statistics
import time

MODEL = "Helsinki-NLP/opus-mt-ru-es"

PHRASES = [
    "Нет, брат, ты чего тут делаешь?",
    "Опять пьяный, мать твою? Я же сказал, иди домой!",
    "Слышь, у меня тут полно работы, помоги",
    "Ладно, давай быстро, нам надо успеть до ночи",
    "Ты опять всё испортил, как всегда",
    "Короче, забей, потом разберёмся",
    "Погоди, я сейчас подойду",
    "Это бабки и дети, уважай людей",
]


def main() -> None:
    import torch
    from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

    print("=== Загрузка локальной модели перевода ===")
    t0 = time.time()
    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForSeq2SeqLM.from_pretrained(MODEL, dtype=torch.float16)
    model = model.to("cuda").eval()
    print(f"модель загружена за {time.time() - t0:.1f} с")

    def tr(text: str) -> tuple[str, float]:
        t0 = time.perf_counter()
        batch = tok([text], return_tensors="pt", padding=True).to("cuda")
        with torch.inference_mode():
            out = model.generate(**batch, max_new_tokens=96, num_beams=1)
        res = tok.batch_decode(out, skip_special_tokens=True)[0]
        return res, time.perf_counter() - t0

    print("\n=== Задержка перевода (локально, GPU) ===")
    times = []
    for p in PHRASES:
        # прогрев
        if not times:
            tr("Привет")
        res, dt = tr(p)
        times.append(dt)
        print(f"  {dt * 1000:6.0f} мс | {p[:34]:<34} -> {res[:34]}")

    print(f"\n  среднее:  {statistics.mean(times) * 1000:.0f} мс")
    print(f"  медиана:  {statistics.median(times) * 1000:.0f} мс")
    print(f"  максимум: {max(times) * 1000:.0f} мс")

    asr = 0.15
    tts = 0.40
    tr_avg = statistics.mean(times)
    print("\n=== ИТОГОВАЯ ЗАДЕРЖКА КОНВЕЙЕРА ===")
    print(f"  ASR (Whisper turbo, GPU):  {asr * 1000:5.0f} мс")
    print(f"  перевод (локально, GPU):   {tr_avg * 1000:5.0f} мс")
    print(f"  TTS XTTS (первый звук):    {tts * 1000:5.0f} мс")
    print(f"  --------------------------------------")
    print(f"  ИТОГО:                     {(asr + tr_avg + tts) * 1000:5.0f} мс")
    print(f"  (было с сетевым переводом: ~2318 мс)")


if __name__ == "__main__":
    main()
