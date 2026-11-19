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

# Языки речи собеседника, которые распознаёт Whisper.
# Прямой модели перевода на русский есть только у es/en/it — для остальных
# используется запасной путь: Whisper сам переводит на английский
# (task="translate"), затем eng->ru. Поэтому языков много, а моделей мало.
PEER_LANGS: tuple[tuple[str, str], ...] = (
    ("auto", "авто (определить самому)"),
    ("es", "Испанский"),
    ("en", "Английский"),
    ("ru", "Русский"),
    ("uk", "Украинский"),
    ("pl", "Польский"),
    ("cs", "Чешский"),
    ("sk", "Словацкий"),
    ("bg", "Болгарский"),
    ("sr", "Сербский"),
    ("hr", "Хорватский"),
    ("sl", "Словенский"),
    ("mk", "Македонский"),
    ("bs", "Боснийский"),
    ("ro", "Румынский"),
    ("hu", "Венгерский"),
    ("tr", "Турецкий"),
    ("el", "Греческий"),
    ("de", "Немецкий"),
    ("fr", "Французский"),
    ("it", "Итальянский"),
    ("pt", "Португальский"),
    ("nl", "Нидерландский"),
    ("da", "Датский"),
    ("sv", "Шведский"),
    ("no", "Норвежский"),
    ("fi", "Финский"),
    ("et", "Эстонский"),
    ("lv", "Латышский"),
    ("lt", "Литовский"),
    ("ar", "Арабский"),
    ("he", "Иврит"),
    ("fa", "Персидский"),
    ("hi", "Хинди"),
    ("bn", "Бенгальский"),
    ("ur", "Урду"),
    ("ta", "Тамильский"),
    ("th", "Тайский"),
    ("vi", "Вьетнамский"),
    ("id", "Индонезийский"),
    ("ms", "Малайский"),
    ("tl", "Филиппинский"),
    ("ja", "Японский"),
    ("ko", "Корейский"),
    ("zh", "Китайский"),
    ("sw", "Суахили"),
    ("af", "Африкаанс"),
)

# Коды языков, которые движок принимает для чужой речи.
PEER_LANG_CODES: tuple[str, ...] = tuple(code for code, _t in PEER_LANGS)

DEFAULT_LANG = "es"
# Мегрельский (mg) УДАЛЁН: требовал две MT-модели (~900 МБ) + голос Piper,
# из-за чего память росла до 8 ГБ, а выгрузка не освобождала её до конца.
LANG_ORDER = ("es", "en", "ow", "it")


def titles() -> list[tuple[str, str]]:
    """Список (код, название) в порядке показа в интерфейсе."""
    return [(code, LANGS[code]["title"]) for code in LANG_ORDER]


def mt_model(code: str) -> list:
    """Модели перевода ru -> язык.

    Элемент — либо строка (имя модели), либо кортеж (имя, target-токен).
    Кортеж нужен для мультиязычных моделей (opus-mt-en-mul), где язык
    цели задаётся токеном вида >>kat<<.
    """
    m = info(code)["mt"]
    return list(m) if isinstance(m, (list, tuple)) else [m]


def mt_names(code: str) -> list[str]:
    """Только имена моделей (для кэша и логов)."""
    out = []
    for item in mt_model(code):
        out.append(item[0] if isinstance(item, (list, tuple)) else item)
    return out


def stylizer(code: str) -> str:
    """Имя модуля-стилизатора для языка ('' — не нужен)."""
    return info(code).get("stylizer", "")


def piper_voice(code: str) -> str:
    """Голос Piper для языка ('' — XTTS достаточно)."""
    return info(code).get("piper", "")


def can_clone(code: str) -> bool:
    """Умеет ли XTTS клонировать голос на этом языке."""
    return bool(info(code).get("clone", True))


def peer_titles() -> list[tuple[str, str]]:
    """Список языков речи собеседника (код, название)."""
    return list(PEER_LANGS)


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
