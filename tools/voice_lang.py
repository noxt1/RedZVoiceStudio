"""Языки озвучки и перевода: испанский, английский, олдвест, итальянский.

Модуль общий для движка (tools/live_translate.py) и приложения (app/):
  * движок берёт отсюда код языка XTTS ("es"/"en"/"it") и модель перевода
    (Helsinki-NLP/opus-mt-ru-XX);
  * приложение берёт названия языков для выбора в интерфейсе и суффиксы
    имён файлов озвучки.

«Олдвест» (ow) — это НЕ отдельный язык, а английский в стиле вестерна:
перевод делается на английский, потом переписывается словами ковбойской
речи (to_oldwest). XTTS при этом остаётся английским — тот же голос,
другая лексика и интонация. Дополнительной модели и задержки это не даёт.

Суффиксы имён файлов: испанский — основной (mx_01.mp3, как раньше, чтобы
не ломать ресурс сервера), остальные — с суффиксом (mx_01_en.mp3).
"""

from __future__ import annotations

import re

# Импортируем новый Western Style Engine
from western_style import WesternStyle, WesternStyleEngine, style_to_western, to_oldwest as _new_to_oldwest

# Коды языков -> параметры.
#   title  — название для интерфейса
#   xtts   — код языка для XTTS ("es", "en", "it")
#   mt     — модель перевода ru -> язык
#   field  — поле в lines.json с текстом реплики
#   suffix — суффикс файла озвучки ("" у испанского — основного)
LANGS: dict[str, dict] = {
    "es": {
        "title": "Испанский",
        "xtts": "es",
        "mt": "Helsinki-NLP/opus-mt-ru-es",
        "field": "es",
        "suffix": "",
    },
    "en": {
        "title": "Английский",
        "xtts": "en",
        "mt": "Helsinki-NLP/opus-mt-ru-en",
        "field": "en",
        "suffix": "_en",
    },
    "ow": {
        "title": "Олдвест (английский, вестерн)",
        "xtts": "en",
        "mt": "Helsinki-NLP/opus-mt-ru-en",
        "field": "ow",
        "suffix": "_ow",
    },
    "it": {
        "title": "Итальянский",
        "xtts": "it",
        # Прямой модели ru->it у Helsinki-NLP нет, поэтому цепочка:
        # русский -> испанский -> итальянский. Дополнительная задержка
        # около 80 мс, зато качество заметно лучше машинного перевода.
        "mt": ["Helsinki-NLP/opus-mt-ru-es", "Helsinki-NLP/opus-mt-es-it"],
        "field": "it",
        "suffix": "_it",
    },
}

# Перевод С ЧУЖОГО языка на русский — для перехвата речи других игроков.
# Пустая цепочка = перевод не нужен (текст уже на русском).
REVERSE_MT: dict[str, list[str]] = {
    "es": ["Helsinki-NLP/opus-mt-es-ru"],
    "en": ["Helsinki-NLP/opus-mt-en-ru"],
    "it": ["Helsinki-NLP/opus-mt-it-es", "Helsinki-NLP/opus-mt-es-ru"],
    "ru": [],
}

DEFAULT_LANG = "es"
LANG_ORDER = ("es", "en", "ow", "it")


def titles() -> list[tuple[str, str]]:
    """Список (код, название) в порядке показа в интерфейсе."""
    return [(code, LANGS[code]["title"]) for code in LANG_ORDER]


def info(code: str) -> dict:
    """Параметры языка (для неизвестного кода — испанский)."""
    return LANGS.get(code, LANGS[DEFAULT_LANG])


def xtts_lang(code: str) -> str:
    """Код языка для XTTS."""
    return info(code)["xtts"]


def mt_model(code: str) -> list[str]:
    """Модели перевода ru -> язык (одна или цепочка)."""
    m = info(code)["mt"]
    return list(m) if isinstance(m, (list, tuple)) else [m]


def reverse_mt(src: str) -> list[str]:
    """Модели перевода язык -> русский (для перехвата чужих игроков)."""
    return list(REVERSE_MT.get(src, []))


def field(code: str) -> str:
    """Поле в lines.json с текстом на этом языке."""
    return info(code)["field"]


def suffix(code: str) -> str:
    """Суффикс файла озвучки для этого языка."""
    return info(code)["suffix"]


def title(code: str) -> str:
    """Название языка для интерфейса."""
    return info(code)["title"]


def phrase_name(phrase_id: str, code: str) -> str:
    """Имя файла озвучки: mx_01 (испанский), mx_01_en (английский) и т.п."""
    return f"mx_{phrase_id}{suffix(code)}"


# --------------------------------------------------------------------------
# Олдвест / Western Style Engine
# --------------------------------------------------------------------------
# Старые словари (_OW_EXACT, _OW_WORDS, ...) оставлены для обратной
# совместимости, но фактическая стилизация теперь выполняется через
# WesternStyleEngine (tools/western_style.py).
# Новый движок НЕ добавляет «partner» автоматически в конец фраз.

# Экземпляр движка с классическим стилем по умолчанию.
_western_engine = WesternStyleEngine(WesternStyle.CLASSIC)


def set_western_style(style: str) -> str:
    """Установить профиль стилизации: light / classic / strong.

    Возвращает текущий профиль.
    """
    global _western_engine
    s = (style or "classic").lower().strip()
    if s == "light":
        _western_engine.set_style(WesternStyle.LIGHT)
    elif s == "strong":
        _western_engine.set_style(WesternStyle.STRONG)
    else:
        _western_engine.set_style(WesternStyle.CLASSIC)
        s = "classic"
    return s


def get_western_style() -> str:
    """Вернуть текущий профиль стилизации (light / classic / strong)."""
    return _western_engine.style.value


def to_oldwest(text: str) -> str:
    """Стилизовать английский текст в стиле Дикого Запада.

    Использует WesternStyleEngine (классический профиль по умолчанию).
    Не добавляет partner автоматически в конец предложений.
    """
    return _western_engine.style_text(text or "")
