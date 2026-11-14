"""Перевод русских фраз на испанский (для озвучки).

Используется свободный endpoint Google Translate. Если сеть недоступна,
фраза остаётся как есть, а озвучка XTTS всё равно прозвучит — просто
с русским текстом (модель справится, но акцент будет слабее).
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request

RU_RE = re.compile(r"[А-Яа-яЁё]")


def looks_russian(text: str) -> bool:
    return bool(RU_RE.search(text))


def translate_ru_to(text: str, target: str = "es", timeout: float = 12.0,
                    retries: int = 3) -> tuple[str, bool]:
    """Перевести русский текст на нужный язык.

    target: es / en / it (для остальных — оставляем как есть).

    Возвращает (перевод, успех).

    Сеть периодически подкидывает разовые сбои, поэтому делаем несколько
    попыток. Если перевод не удался — возвращаем исходный текст: XTTS всё
    равно его озвучит, просто с русским произношением.
    """
    if not text.strip():
        return text, True
    if not looks_russian(text):
        return text, True
    if target not in ("es", "en", "it"):
        return text, False

    url = ("https://translate.googleapis.com/translate_a/single?client=gtx"
           f"&sl=ru&tl={target}&dt=t&q={urllib.parse.quote(text)}")
    last_error = ""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))
            parts = [chunk[0] for chunk in data[0] if chunk and chunk[0]]
            result = "".join(parts).strip()
            if result:
                return result, True
            last_error = "пустой ответ"
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}: {exc}"
        time.sleep(0.6 * (attempt + 1))
    print(f"[translate] не удалось перевести ({last_error})")
    return text, False


def translate_ru_to_es(text: str, timeout: float = 12.0, retries: int = 3) -> tuple[str, bool]:
    """Вернуть (испанский текст, успех)."""
    return translate_ru_to(text, "es", timeout, retries)


def translate_all_languages(text: str) -> dict[str, str]:
    """Перевести русскую фразу на все языки сразу.

    Возвращает {"es": ..., "en": ..., "it": ..., "ow": ...}.
    Олдвест — это английский, переписанный словами ковбойской речи.
    """
    out = {"es": text, "en": "", "it": "", "ow": ""}
    if not text.strip() or not looks_russian(text):
        return out
    es, _ = translate_ru_to(text, "es")
    en, _ = translate_ru_to(text, "en")
    it, _ = translate_ru_to(text, "it")
    out["es"] = es
    out["en"] = en
    out["it"] = it
    try:
        import studio_core
        out["ow"] = studio_core.to_oldwest(en or text)
    except Exception:
        out["ow"] = en or text
    return out


def normalize_for_speech(text: str) -> str:
    """Мелкая чистка текста перед синтезом."""
    text = text.strip().strip('"')
    text = re.sub(r"\s+", " ", text)
    return text
