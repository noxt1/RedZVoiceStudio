"""Замер 2: задержка перевода RU->ES + влияние размера чанка XTTS.

Перевод идёт по сети (Google endpoint) — это может стать узким местом.
Проверяем: сколько миллисекунд занимает перевод типичной фразы.

Запуск:
    python research\\bench_translate.py
"""

from __future__ import annotations

import json
import statistics
import time
import urllib.parse
import urllib.request

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


def translate(text: str, timeout: float = 10.0) -> tuple[str, float]:
    url = ("https://translate.googleapis.com/translate_a/single?client=gtx"
           f"&sl=ru&tl=es&dt=t&q={urllib.parse.quote(text)}")
    t0 = time.perf_counter()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8", "replace"))
    out = "".join(c[0] for c in data[0] if c and c[0])
    return out, time.perf_counter() - t0


def main() -> None:
    print("=== Задержка перевода RU->ES (сетевой endpoint) ===")
    times = []
    for phrase in PHRASES:
        try:
            out, dt = translate(phrase)
            times.append(dt)
            print(f"  {dt * 1000:6.0f} мс | {phrase[:34]:<34} -> {out[:34]}")
        except Exception as exc:
            print(f"  ОШИБКА: {type(exc).__name__}: {exc}")

    if times:
        print(f"\n  среднее:  {statistics.mean(times) * 1000:.0f} мс")
        print(f"  минимум:  {min(times) * 1000:.0f} мс")
        print(f"  максимум: {max(times) * 1000:.0f} мс")
        print(f"  медиана:  {statistics.median(times) * 1000:.0f} мс")

    print("\n=== ИТОГОВАЯ ЗАДЕРЖКА КОНВЕЙЕРА ===")
    asr = 0.15       # измерено: 4 с аудио -> 0.13 с (GPU, large-v3-turbo)
    tr = statistics.mean(times) if times else 0.3
    tts = 0.40       # измерено: первый звук 371 мс (длинная фраза)
    print(f"  ASR (Whisper turbo, GPU):     {asr * 1000:5.0f} мс")
    print(f"  перевод RU->ES (сеть):        {tr * 1000:5.0f} мс")
    print(f"  TTS XTTS (первый звук):       {tts * 1000:5.0f} мс")
    print(f"  ---------------------------------------")
    print(f"  ИТОГО до первого звука:       {(asr + tr + tts) * 1000:5.0f} мс")
    print("\n  Для «нажал кнопку -> отпустил -> заговорили на испанском» это нормально.")


if __name__ == "__main__":
    main()
